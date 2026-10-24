from fastapi import APIRouter, HTTPException, Depends, Header
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, date
import uuid

from backend.database import get_db
from backend.models import User, Company, Scenario, IntegrationSource, VerificationCode, UserCompany
from backend.schemas import (
    UserRegisterRequest, UserLoginRequest, UserOut, CompanyOut, CompanyCreate,
    AuthResponse, UserProfileUpdate, CompanyUpdate,
    SendCodeRequest, SendCodeResponse, VerifyCodeRequest, VerifyCodeResponse
)
from backend.core.security import hash_password, verify_password, create_access_token, decode_access_token
from backend.core.email_service import send_verification_email
from backend.routers.scenarios import DEFAULT_SCENARIOS
from backend.routers.integrations import DEFAULT_INTEGRATION_CONFIGS
import random
from datetime import timedelta

router = APIRouter(prefix="/auth", tags=["Боевая авторизация и Личный кабинет"])

def get_current_user_optional(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """Helper to extract user from Bearer token"""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.split(" ")[1]
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        return None
    user_id = payload["sub"]
    return db.query(User).filter(User.id == user_id).first()

def get_current_user_required(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
) -> User:
    user = get_current_user_optional(authorization, db)
    if not user:
        raise HTTPException(status_code=401, detail="Требуется авторизация")
    return user

@router.post("/register", response_model=AuthResponse)
def register(payload: UserRegisterRequest, db: Session = Depends(get_db)):
    """
    Боевая регистрация предпринимателя:
    - Почта (Email)
    - Пароль (хэширование)
    - ФИО
    - Форма собственности (ООО, ИП, Самозанятый, АО)
    - Название компании
    - ИНН (строка с сохранением ведущих нулей)
    - Отрасль и налоговый режим
    - Если выписка еще не загружена -> has_statement = False («чистый бизнес»)
    """
    # 0. Валидация входных данных
    clean_inn = str(payload.inn).strip()
    if not clean_inn or not clean_inn.isdigit():
        raise HTTPException(status_code=400, detail="ИНН должен состоять только из цифр")
    if payload.legal_form in ["ООО", "АО"] and len(clean_inn) != 10:
        raise HTTPException(status_code=400, detail="ИНН юридического лица (ООО, АО) должен содержать ровно 10 цифр")
    if payload.legal_form in ["ИП", "Самозанятый"] and len(clean_inn) != 12:
        raise HTTPException(status_code=400, detail="ИНН индивидуального предпринимателя или самозанятого должен содержать ровно 12 цифр")
    if len(payload.company_name.strip()) < 2:
        raise HTTPException(status_code=400, detail="Название компании должно содержать минимум 2 символа")
    if len(payload.full_name.strip()) < 3:
        raise HTTPException(status_code=400, detail="Укажите корректное ФИО предпринимателя")

    # 1. Проверка уникальности email
    existing_user = db.query(User).filter(User.email == payload.email.lower().strip()).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Пользователь с таким email уже зарегистрирован")

    # 2. Создаем уникальный ID компании
    company_id = f"U_{uuid.uuid4().hex[:6].upper()}"

    # 3. Создаем компанию
    comp = Company(
        id=company_id,
        name=payload.company_name.strip(),
        inn=str(payload.inn).strip(),
        legal_form=payload.legal_form,
        industry=payload.industry,
        overdraft_limit=float(payload.overdraft_limit or 0.0),
        tax_regime=payload.tax_regime,
        tax_regime_confirmed=True,
        has_statement=False,  # «Чистый бизнес» до подгрузки выписки
        initial_manual_balance=float(payload.initial_balance or 0.0),
        last_balance=float(payload.initial_balance or 0.0),
        operations_count=0,
        data_quality_score=100.0
    )
    db.add(comp)

    # 4. Создаем пользователя
    user_id = f"usr_{uuid.uuid4().hex[:8]}"
    raw_pw = payload.password if payload.password else f"otp_{uuid.uuid4().hex}"
    new_user = User(
        id=user_id,
        email=payload.email.lower().strip(),
        password_hash=hash_password(raw_pw),
        full_name=payload.full_name.strip(),
        phone=payload.phone.strip() if payload.phone else None,
        role="owner",
        company_id=company_id,
        is_active=True,
        last_login_at=datetime.utcnow()
    )
    db.add(new_user)
    comp.created_by_user_id = user_id

    # 4.5 Привязываем компанию к аккаунту в связующей таблице
    uc = UserCompany(
        user_id=user_id,
        company_id=company_id,
        role="owner",
        is_default=True
    )
    db.add(uc)

    # 5. Инициализируем интеграции и сценарии для новой компании
    for dic in DEFAULT_INTEGRATION_CONFIGS:
        src = IntegrationSource(
            company_id=company_id,
            adapter_name=dic["adapter_name"],
            display_name=dic["display_name"],
            description=dic["description"],
            status=dic["status"],
            events_added=0,
            last_sync_at=datetime.utcnow()
        )
        db.add(src)

    for ds in DEFAULT_SCENARIOS:
        sc = Scenario(
            id=f"{ds['id']}_{company_id}",
            company_id=company_id,
            name=ds["name"],
            scenario_type=ds["scenario_type"],
            params=ds["params"]
        )
        db.add(sc)

    db.commit()
    db.refresh(new_user)
    db.refresh(comp)

    # 6. Создаем JWT токен
    token = create_access_token({"sub": new_user.id, "email": new_user.email, "company_id": company_id})

    return AuthResponse(
        access_token=token,
        token_type="bearer",
        user=UserOut.model_validate(new_user),
        company=CompanyOut.model_validate(comp)
    )

@router.post("/send-code", response_model=SendCodeResponse)
def send_code(payload: SendCodeRequest, db: Session = Depends(get_db)):
    """
    Генерирует и отправляет 6-значный код на указанный email через SMTP.
    """
    email = payload.email.lower().strip()
    if "@" not in email or "." not in email:
        raise HTTPException(status_code=400, detail="Укажите корректный email адрес")

    code = f"{random.randint(100000, 999999)}"
    now = datetime.utcnow()
    expires_at = now + timedelta(minutes=10)

    # Деактивируем предыдущие коды
    db.query(VerificationCode).filter(
        VerificationCode.email == email,
        VerificationCode.is_used == False
    ).update({"is_used": True})

    vc = VerificationCode(
        id=f"vc_{uuid.uuid4().hex[:12]}",
        email=email,
        code=code,
        created_at=now,
        expires_at=expires_at,
        is_used=False,
        attempts=0
    )
    db.add(vc)
    db.commit()

    # Отправляем письмо через SMTP
    send_verification_email(email, code)

    existing_user = db.query(User).filter(User.email == email).first()
    is_registered = existing_user is not None

    return SendCodeResponse(
        success=True,
        message=f"Код подтверждения отправлен на {email}",
        is_registered=is_registered,
        dev_code=code
    )

@router.post("/verify-code", response_model=VerifyCodeResponse)
def verify_code(payload: VerifyCodeRequest, db: Session = Depends(get_db)):
    """
    Проверяет 6-значный код.
    Если пользователь уже зарегистрирован -> авторизует и выдает токен.
    Если новый -> подтверждает email для продолжения регистрации бизнеса.
    """
    email = payload.email.lower().strip()
    code = payload.code.strip()

    vc = db.query(VerificationCode).filter(
        VerificationCode.email == email,
        VerificationCode.code == code,
        VerificationCode.is_used == False
    ).order_by(VerificationCode.created_at.desc()).first()

    if not vc:
        raise HTTPException(status_code=400, detail="Неверный код подтверждения")

    if datetime.utcnow() > vc.expires_at:
        raise HTTPException(status_code=400, detail="Срок действия кода истек. Запросите новый код.")

    vc.is_used = True
    db.commit()

    user = db.query(User).filter(User.email == email).first()
    if user:
        user.last_login_at = datetime.utcnow()
        db.commit()

        comp = db.query(Company).filter(Company.id == user.company_id).first()
        if not comp:
            comp = db.query(Company).first()

        token = create_access_token({"sub": user.id, "email": user.email, "company_id": comp.id})

        return VerifyCodeResponse(
            status="authenticated",
            is_registered=True,
            message="Вход выполнен успешно!",
            access_token=token,
            user=UserOut.model_validate(user),
            company=CompanyOut.model_validate(comp)
        )
    else:
        return VerifyCodeResponse(
            status="needs_registration",
            is_registered=False,
            message="Email подтвержден! Заполните реквизиты бизнеса для завершения регистрации."
        )

@router.post("/login", response_model=AuthResponse)
def login(payload: UserLoginRequest, db: Session = Depends(get_db)):
    """
    Боевая авторизация по email и паролю
    """
    user = db.query(User).filter(User.email == payload.email.lower().strip()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Неверный email или пароль")

    user.last_login_at = datetime.utcnow()
    db.commit()

    comp = db.query(Company).filter(Company.id == user.company_id).first()
    if not comp:
        comp = db.query(Company).first()

    token = create_access_token({"sub": user.id, "email": user.email, "company_id": comp.id})

    return AuthResponse(
        access_token=token,
        token_type="bearer",
        user=UserOut.model_validate(user),
        company=CompanyOut.model_validate(comp)
    )

@router.get("/me")
def get_current_profile(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Возвращает данные текущего авторизованного пользователя и его компаний.
    Если пользователь не авторизован (гостевой режим), возвращает authenticated: False.
    """
    user = get_current_user_optional(authorization, db)
    if not user:
        return {
            "authenticated": False,
            "user": None,
            "company": None,
            "companies": []
        }

    # Все компании, привязанные к пользователю
    ucs = db.query(UserCompany).filter(UserCompany.user_id == user.id).all()
    comp_ids = [uc.company_id for uc in ucs]
    if user.company_id and user.company_id not in comp_ids:
        comp_ids.append(user.company_id)
        uc = UserCompany(user_id=user.id, company_id=user.company_id, role="owner", is_default=True)
        db.add(uc)
        db.commit()

    user_companies = db.query(Company).filter(Company.id.in_(comp_ids)).all() if comp_ids else []
    comp = next((c for c in user_companies if c.id == user.company_id), None)
    if not comp and user_companies:
        comp = user_companies[0]
        user.company_id = comp.id
        db.commit()

    return {
        "authenticated": True,
        "user": UserOut.model_validate(user),
        "company": CompanyOut.model_validate(comp) if comp else None,
        "companies": [CompanyOut.model_validate(c) for c in user_companies]
    }

@router.patch("/profile", response_model=UserOut)
def update_profile(
    payload: UserProfileUpdate,
    user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    if payload.full_name is not None:
        user.full_name = payload.full_name.strip()
    if payload.phone is not None:
        user.phone = payload.phone.strip()
    if payload.company_id is not None:
        comp_id = payload.company_id.strip()
        comp = db.query(Company).filter(Company.id == comp_id).first()
        if comp:
            user.company_id = comp_id
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)

@router.post("/switch-company/{company_id}")
def switch_company(
    company_id: str,
    user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    Переключение текущего активного бизнеса пользователя с фиксацией в БД.
    """
    if user.role != "bank_manager":
        uc = db.query(UserCompany).filter(
            UserCompany.user_id == user.id,
            UserCompany.company_id == company_id
        ).first()
        if not uc and user.company_id != company_id and company_id not in ["C001", "C004"]:
            raise HTTPException(status_code=403, detail="Нет доступа к этой компании")

        # Обновляем признак по умолчанию в связях
        db.query(UserCompany).filter(UserCompany.user_id == user.id).update({UserCompany.is_default: False})
        if uc:
            uc.is_default = True

    comp = db.query(Company).filter(Company.id == company_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Компания не найдена")

    user.company_id = company_id
    db.commit()
    db.refresh(user)

    return {
        "status": "ok",
        "company_id": user.company_id,
        "company_name": comp.name
    }

@router.patch("/company", response_model=CompanyOut)
def update_user_company(
    payload: CompanyUpdate,
    user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    comp = db.query(Company).filter(Company.id == user.company_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Компания не найдена")

    if payload.name is not None:
        comp.name = payload.name.strip()
    if payload.legal_form is not None:
        comp.legal_form = payload.legal_form
    if payload.industry is not None:
        comp.industry = payload.industry
    if payload.overdraft_limit is not None:
        comp.overdraft_limit = payload.overdraft_limit
    if payload.tax_regime is not None:
        comp.tax_regime = payload.tax_regime
    if payload.tax_regime_confirmed is not None:
        comp.tax_regime_confirmed = payload.tax_regime_confirmed
    if payload.initial_manual_balance is not None:
        comp.initial_manual_balance = payload.initial_manual_balance
        if payload.initial_manual_balance == 0:
            from backend.models import Operation
            last_op = db.query(Operation).filter(Operation.company_id == comp.id).order_by(Operation.operation_date.desc(), Operation.id.desc()).first()
            if last_op:
                comp.last_balance = float(last_op.balance_eod)
            else:
                comp.last_balance = 0.0
        else:
            comp.last_balance = payload.initial_manual_balance

    if payload.last_balance is not None:
        comp.last_balance = payload.last_balance
        comp.initial_manual_balance = payload.last_balance

    db.commit()
    db.refresh(comp)
    return CompanyOut.model_validate(comp)
