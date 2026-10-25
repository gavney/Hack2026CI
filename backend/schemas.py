from datetime import date, datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

# --- Auth & User ---
class UserRegisterRequest(BaseModel):
    email: str
    password: Optional[str] = None
    full_name: str  # ФИО
    phone: Optional[str] = None
    legal_form: str = "ИП"  # ООО, ИП, Самозанятый, АО
    company_name: str
    inn: str
    industry: str = "Торговля и услуги"
    tax_regime: str = "УСН Доходы 6%"
    initial_balance: float = 0.0
    overdraft_limit: float = 0.0

class UserLoginRequest(BaseModel):
    email: str
    password: str

class SendCodeRequest(BaseModel):
    email: str

class SendCodeResponse(BaseModel):
    success: bool
    message: str
    is_registered: bool = False
    dev_code: Optional[str] = None

class VerifyCodeRequest(BaseModel):
    email: str
    code: str

class UserProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    company_id: Optional[str] = None

class UserOut(BaseModel):
    id: str
    email: str
    full_name: str
    phone: Optional[str] = None
    role: str = "owner"
    company_id: Optional[str] = None
    is_active: bool = True

    class Config:
        from_attributes = True

# --- Company ---
class CompanyBase(BaseModel):
    id: str
    name: str
    inn: str
    legal_form: Optional[str] = None
    industry: Optional[str] = None
    overdraft_limit: float = 0.0
    tax_regime: str = "УСН Доходы 6%"
    tax_regime_confirmed: bool = False
    has_statement: bool = True
    initial_manual_balance: float = 0.0
    forecast_model: Optional[str] = "ml-ridge-lgbm"
    forecast_simulations: Optional[int] = 1000
    forecast_confidence_level: Optional[float] = 0.90
    ml_categorizer_threshold: Optional[float] = 0.60
    gigachat_enabled: Optional[bool] = False

class CompanyCreate(BaseModel):
    name: str
    inn: str
    legal_form: Optional[str] = "ООО"
    industry: Optional[str] = "Оптовая торговля"
    overdraft_limit: Optional[float] = 0.0
    tax_regime: Optional[str] = "УСН Доходы 6%"
    initial_balance: Optional[float] = 0.0

class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    legal_form: Optional[str] = None
    industry: Optional[str] = None
    overdraft_limit: Optional[float] = None
    tax_regime: Optional[str] = None
    tax_regime_confirmed: Optional[bool] = None
    initial_manual_balance: Optional[float] = None
    last_balance: Optional[float] = None

class CompanyOut(CompanyBase):
    first_operation_date: Optional[date] = None
    last_operation_date: Optional[date] = None
    operations_count: int = 0
    last_balance: float = 0.0
    average_daily_turnover: float = 0.0
    data_quality_score: float = 100.0

    class Config:
        from_attributes = True

class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
    company: CompanyOut

class VerifyCodeResponse(BaseModel):
    status: str  # "authenticated" | "needs_registration"
    message: str
    access_token: Optional[str] = None
    user: Optional[UserOut] = None
    company: Optional[CompanyOut] = None
    is_registered: bool = False

class StatementUploadResult(BaseModel):
    status: str
    message: str
    operations_count: int
    first_date: Optional[str] = None
    last_date: Optional[str] = None
    last_balance: float = 0.0
    quality_score: float = 100.0
    slots_count: int = 0
    has_statement: bool = True
    warnings: Optional[List[str]] = None

class StatementUploadHistoryOut(BaseModel):
    id: str
    company_id: str
    filename: str
    file_size_bytes: int
    uploaded_at: datetime
    status: str
    operations_count: int
    slots_detected: int
    last_balance: float
    data_quality_score: float
    execution_time_sec: float

    class Config:
        from_attributes = True

class StatementUploadTaskResponse(BaseModel):
    task_id: str
    status: str
    message: str

class StatementProgressResponse(BaseModel):
    task_id: str
    status: str
    stage: str
    stage_text: str
    progress_pct: int
    filename: Optional[str] = None
    file_size_mb: float = 0.0
    processed_rows: int = 0
    total_rows: int = 0
    speed_rows_per_sec: float = 0.0
    elapsed_seconds: float = 0.0
    eta_seconds: float = 0.0
    result: Optional[StatementUploadResult] = None
    error: Optional[str] = None

# --- Categories ---
class CategoryBase(BaseModel):
    id: str
    name: str
    cashflow_role: str = "variable_out"
    parent_id: Optional[str] = None
    color: str = "#10b981"
    icon: str = "tag"
    hidden: bool = False

class CategoryCreate(BaseModel):
    id: Optional[str] = None
    name: str
    cashflow_role: str = "variable_out"
    parent_id: Optional[str] = None
    color: str = "#10b981"
    icon: str = "tag"
    hidden: bool = False
    company_id: Optional[str] = None

class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    cashflow_role: Optional[str] = None
    parent_id: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    hidden: Optional[bool] = None

class CategoryOut(CategoryBase):
    company_id: Optional[str] = None
    status: str = "confirmed"
    version: int = 1

    class Config:
        from_attributes = True

# --- Operations ---
class OperationOut(BaseModel):
    id: int
    company_id: str
    operation_id: Optional[str] = None
    operation_date: date
    amount: float
    direction: str
    counterparty_inn: Optional[str] = None
    counterparty_name: Optional[str] = None
    payment_purpose: Optional[str] = None
    balance_eod: float
    category_id: Optional[str] = None
    category_name: Optional[str] = None
    category_confidence: float = 1.0
    category_source: str = "rule"
    is_duplicate: bool = False
    vat_amount: Optional[float] = None
    vat_flag: Optional[int] = None
    is_cash_gap_critical: bool = False

    class Config:
        from_attributes = True

class OperationCategoryUpdate(BaseModel):
    category_id: str
    apply_to_similar: bool = False  # Save to memory by (normalized purpose + counterparty_inn)

class OperationCreate(BaseModel):
    operation_date: date
    amount: float
    direction: str  # Поступление | Списание
    category_id: Optional[str] = "cat_other_out"
    counterparty_name: Optional[str] = "Контрагент"
    counterparty_inn: Optional[str] = ""
    payment_purpose: Optional[str] = "Ручная операция"

# --- Slots ---
class SlotCreate(BaseModel):
    category_id: str
    direction: str = "Списание"
    day_of_month: int = 10
    typical_amount: float
    counterparty_name: Optional[str] = None
    counterparty_inn: Optional[str] = ""

class SlotOut(BaseModel):
    id: int
    company_id: str
    category_id: str
    category_name: Optional[str] = None
    counterparty_inn: Optional[str] = None
    counterparty_name: Optional[str] = None
    direction: str
    day_of_month: int
    typical_amount: float
    share_of_months: float
    confirmed_by_user: bool
    is_active: bool

    class Config:
        from_attributes = True

class SlotUpdate(BaseModel):
    typical_amount: Optional[float] = None
    day_of_month: Optional[int] = None
    confirmed_by_user: Optional[bool] = None
    is_active: Optional[bool] = None

# --- Events (Future Cashflow) ---
class EventBase(BaseModel):
    event_date: date
    amount: float  # Signed: positive for inflow, negative for outflow
    probability: float = 1.0
    category_id: Optional[str] = None
    counterparty_inn: Optional[str] = None
    counterparty_name: Optional[str] = None
    source: str = "manual"
    status: str = "expected"
    is_active: bool = True
    note: Optional[str] = None

class EventCreate(EventBase):
    pass

class EventUpdate(BaseModel):
    event_date: Optional[date] = None
    amount: Optional[float] = None
    probability: Optional[float] = None
    category_id: Optional[str] = None
    counterparty_name: Optional[str] = None
    counterparty_inn: Optional[str] = None
    status: Optional[str] = None
    is_active: Optional[bool] = None
    note: Optional[str] = None

class EventOut(EventBase):
    id: str
    company_id: str
    status: str = "expected"
    is_active: bool = True
    delay_days: int = 0
    actual_amount: Optional[float] = None
    created_at: datetime

    class Config:
        from_attributes = True

# --- Forecast Contract (Section 10.2) ---
class ForecastDayPoint(BaseModel):
    date: date
    p10: float
    p50: float
    p90: float
    prob_negative: float

class ForecastContribution(BaseModel):
    date: date
    category: Optional[str] = "cat_other_out"
    amount: float
    source: str
    probability: Optional[float] = 1.0
    is_slot_replacement: Optional[bool] = False
    overridden_slot_id: Optional[str] = None

class ForecastResultOut(BaseModel):
    model_version: str = "stub-0.1"
    quality: str = "low"
    as_of: date
    horizon: int = 30
    days: List[ForecastDayPoint]
    contributions: List[ForecastContribution]
    total_shortfall_p10: float = 0.0
    first_gap_date: Optional[date] = None
    gap_probability: float = 0.0
    sample_paths: Optional[List[List[float]]] = None
    risk_radar: Optional[Dict[str, Any]] = None
    simulation_meta: Optional[Dict[str, Any]] = None

# --- Minimalist Forecast & ML Settings ---
class ForecastSettingsOut(BaseModel):
    forecast_model: str = "ml-ridge-lgbm"
    forecast_simulations: int = 1000
    forecast_confidence_level: float = 0.90
    ml_categorizer_threshold: float = 0.60
    gigachat_enabled: bool = False
    gigachat_connected: bool = False
    available_models: List[str] = ["ml-ridge-lgbm", "monte-carlo", "stub-0.1"]

class ForecastSettingsUpdate(BaseModel):
    forecast_model: Optional[str] = None
    forecast_simulations: Optional[int] = None
    forecast_confidence_level: Optional[float] = None
    ml_categorizer_threshold: Optional[float] = None
    gigachat_enabled: Optional[bool] = None
    gigachat_credentials: Optional[str] = None

# --- Alerts & Breakdown ---
class ActionRecommendation(BaseModel):
    id: str
    title: str
    description: str
    estimated_effect: float
    action_type: str  # request_prepayment | delay_payment | overdraft_bank

class AlertOut(BaseModel):
    id: str
    company_id: str
    forecast_id: Optional[str] = None
    level: str  # critical | warning | info
    gap_date: Optional[date] = None
    shortfall_p10: float = 0.0
    shortfall_p50: float = 0.0
    probability: float = 0.0
    reason: Optional[str] = None
    actions: Optional[List[ActionRecommendation]] = None
    acknowledged: bool = False
    created_at: datetime

    class Config:
        from_attributes = True

# --- Scenarios ---
class ScenarioCreate(BaseModel):
    name: str
    scenario_type: str  # delayed_payment | revenue_drop | unexpected_expense | cost_increase | custom
    params: Dict[str, Any]

class ScenarioUpdate(BaseModel):
    name: Optional[str] = None
    params: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None

class ScenarioOut(BaseModel):
    id: str
    company_id: str
    name: str
    scenario_type: str
    params: Dict[str, Any]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

# --- Integrations ---
class IntegrationSourceOut(BaseModel):
    id: int
    company_id: str
    adapter_name: str
    display_name: str
    description: Optional[str] = None
    status: str  # active | mock | syncing | error
    last_sync_at: Optional[datetime] = None
    events_added: int = 0
    config: Dict[str, Any] = {}
    last_payload: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True

class IntegrationSyncRequest(BaseModel):
    adapter_name: str
    simulate_delay_seconds: float = 0.5

# --- Quality Report ---
class QualityReportOut(BaseModel):
    company_id: str
    quality_score: float
    total_operations: int
    date_range: str
    duplicate_rows_count: int
    missing_inn_count: int
    missing_purpose_count: int
    gaps_longer_than_7_days: List[Dict[str, Any]]
    balance_jumps_count: int
    negative_balance_days_count: int
    warnings: List[str]


# --- Counterparties & FNS Check (nalogbi + check) ---
class CounterpartyOut(BaseModel):
    id: int
    company_id: str
    inn: str
    name: str
    role: str  # payer | supplier | both
    turnover: float = 0.0
    inflow_sum: float = 0.0
    outflow_sum: float = 0.0
    ops_count: int = 0
    last_op_date: Optional[date] = None

    last_checked_at: Optional[datetime] = None
    has_blocks: bool = False
    blocks_count: int = 0
    blocks_info: Optional[List[Dict[str, Any]]] = None

    risk_level: str = "unknown"  # green | yellow | red | unknown
    reliability_score: int = 100
    negative_factors: Optional[List[str]] = None
    positive_factors: Optional[List[str]] = None
    check_summary: Optional[str] = None
    recommended_action: Optional[str] = None
    include_in_forecast: bool = True

    class Config:
        from_attributes = True


class CounterpartyCheckRequest(BaseModel):
    inn: Optional[str] = None
    api_key: Optional[str] = None


class CounterpartyCreateRequest(BaseModel):
    inn: str
    name: Optional[str] = None
    role: str = "payer"
    include_in_forecast: bool = True
    api_key: Optional[str] = None


class CounterpartyToggleForecastRequest(BaseModel):
    include_in_forecast: bool


class FnsApiKeyRequest(BaseModel):
    api_key: Optional[str] = None

