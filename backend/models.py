from datetime import datetime, date
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, Date, DateTime,
    ForeignKey, Text, JSON, Index, Enum
)
from sqlalchemy.orm import relationship
from backend.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(String(50), primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)  # ФИО предпринимателя
    phone = Column(String(50), nullable=True)
    role = Column(String(50), default="owner")  # owner | accountant | bank_manager
    company_id = Column(String(50), ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True)
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)

    company = relationship("Company", back_populates="users")
    user_companies = relationship("UserCompany", back_populates="user", cascade="all, delete-orphan")


class UserCompany(Base):
    """Many-to-many link: one user account can own and manage multiple businesses"""
    __tablename__ = "user_companies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id = Column(String(50), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(50), default="owner")  # owner | accountant | viewer
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="user_companies")
    company = relationship("Company", back_populates="user_companies")

    __table_args__ = (
        Index("idx_user_company_pair", "user_id", "company_id", unique=True),
    )


class Company(Base):
    __tablename__ = "companies"

    id = Column(String(50), primary_key=True, index=True)  # C001, C002...
    name = Column(String(255), nullable=False)
    inn = Column(String(20), nullable=False, index=True)  # Read/store as string, keep leading zeros
    legal_form = Column(String(50), nullable=True)  # ООО, ИП, Самозанятый, АО
    industry = Column(String(100), nullable=True, index=True)
    overdraft_limit = Column(Float, default=0.0)  # Overdraft limit in rubles
    tax_regime = Column(String(50), default="УСН Доходы 6%")
    tax_regime_confirmed = Column(Boolean, default=False)
    
    # Statement upload state (True if historical statement CSV loaded, False for clean new business)
    has_statement = Column(Boolean, default=True)
    initial_manual_balance = Column(Float, default=0.0)
    created_by_user_id = Column(String(50), nullable=True)
    
    first_operation_date = Column(Date, nullable=True)
    last_operation_date = Column(Date, nullable=True)
    operations_count = Column(Integer, default=0)
    
    # Financial indicators
    last_balance = Column(Float, default=0.0)
    average_daily_turnover = Column(Float, default=0.0)
    data_quality_score = Column(Float, default=100.0)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    users = relationship("User", back_populates="company")
    user_companies = relationship("UserCompany", back_populates="company", cascade="all, delete-orphan")
    operations = relationship("Operation", back_populates="company", cascade="all, delete-orphan")
    categories = relationship("Category", back_populates="company", cascade="all, delete-orphan")
    slots = relationship("Slot", back_populates="company", cascade="all, delete-orphan")
    events = relationship("Event", back_populates="company", cascade="all, delete-orphan")
    forecasts = relationship("Forecast", back_populates="company", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="company", cascade="all, delete-orphan")
    scenarios = relationship("Scenario", back_populates="company", cascade="all, delete-orphan")
    integrations = relationship("IntegrationSource", back_populates="company", cascade="all, delete-orphan")
    counterparties = relationship("Counterparty", back_populates="company", cascade="all, delete-orphan")


class Category(Base):
    __tablename__ = "categories"

    id = Column(String(100), primary_key=True)  # e.g. cat_payroll, cat_tax_enp, cat_revenue
    company_id = Column(String(50), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True)
    parent_id = Column(String(100), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(255), nullable=False)
    
    # Cashflow role as defined in section 3.2.1 / 3.2.3:
    # regular_out | tax | variable_in | variable_out | one_off | transfer_own | refund
    cashflow_role = Column(String(50), nullable=False, default="variable_out", index=True)
    
    status = Column(String(50), default="confirmed")  # confirmed / suggested
    color = Column(String(50), default="#10b981")
    icon = Column(String(50), default="tag")
    hidden = Column(Boolean, default=False)
    version = Column(Integer, default=1)
    
    company = relationship("Company", back_populates="categories")
    parent = relationship("Category", remote_side=[id])
    operations = relationship("Operation", back_populates="category")


class CategoryMemory(Base):
    __tablename__ = "category_memory"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(String(50), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    norm_key = Column(String(500), nullable=False, index=True)  # normalized purpose + INN
    category_id = Column(String(100), ForeignKey("categories.id", ondelete="CASCADE"), nullable=False)
    uses_count = Column(Integer, default=1)
    last_used_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_company_memory_key", "company_id", "norm_key"),
    )


class Operation(Base):
    __tablename__ = "operations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(String(50), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    operation_id = Column(String(100), nullable=True)
    operation_date = Column(Date, nullable=False, index=True)
    amount = Column(Float, nullable=False)
    direction = Column(String(20), nullable=False)  # 'Поступление' | 'Списание'
    
    counterparty_inn = Column(String(20), nullable=True, index=True)  # Always string
    counterparty_name = Column(String(255), nullable=True)
    payment_purpose = Column(Text, nullable=True)
    balance_eod = Column(Float, nullable=False)
    
    category_id = Column(String(100), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True, index=True)
    category_confidence = Column(Float, default=1.0)
    category_source = Column(String(50), default="rule")  # rule | ml | llm | user | memory
    is_duplicate = Column(Boolean, default=False)
    
    company = relationship("Company", back_populates="operations")
    category = relationship("Category", back_populates="operations")

    __table_args__ = (
        Index("idx_op_company_date", "company_id", "operation_date"),
    )


class Slot(Base):
    """Recurring payment or revenue slot detected by algorithm or confirmed by user"""
    __tablename__ = "slots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(String(50), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    category_id = Column(String(100), ForeignKey("categories.id", ondelete="CASCADE"), nullable=False)
    counterparty_inn = Column(String(20), nullable=True)
    counterparty_name = Column(String(255), nullable=True)
    direction = Column(String(20), default="Списание")  # 'Списание' | 'Поступление'
    
    day_of_month = Column(Integer, nullable=False)  # 1..31
    typical_amount = Column(Float, nullable=False)  # Median monthly amount
    share_of_months = Column(Float, nullable=False)  # e.g. 0.85 (85% of months)
    confirmed_by_user = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    
    company = relationship("Company", back_populates="slots")
    category = relationship("Category")


class Event(Base):
    """Future event (cashflow expectation) from any source: slots, invoices, taxes, manual, integrations"""
    __tablename__ = "events"

    id = Column(String(100), primary_key=True)  # ev_001, etc.
    company_id = Column(String(50), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    event_date = Column(Date, nullable=False, index=True)
    amount = Column(Float, nullable=False)  # Signed: positive for inflow, negative for outflow
    probability = Column(Float, default=1.0)  # 0.0 to 1.0
    category_id = Column(String(100), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    
    counterparty_inn = Column(String(20), nullable=True)
    counterparty_name = Column(String(255), nullable=True)
    
    # Source identifier: history | invoice | contract | tax_calendar | manual | scenario | bank_dbo | 1c_odata | fns_ens | marketplace | registry
    source = Column(String(50), nullable=False, default="manual", index=True)
    
    # Status for plan-fact tracking: expected | received_ontime | delayed | missed | amount_mismatch
    status = Column(String(50), default="expected", index=True)
    is_active = Column(Boolean, default=True)  # Активность платежа для включения в прогноз
    delay_days = Column(Integer, default=0)
    actual_amount = Column(Float, nullable=True)
    
    note = Column(Text, nullable=True)
    linked_operation_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    company = relationship("Company", back_populates="events")
    category = relationship("Category")


class Forecast(Base):
    __tablename__ = "forecasts"

    id = Column(String(100), primary_key=True)
    company_id = Column(String(50), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    as_of = Column(Date, nullable=False)
    horizon = Column(Integer, default=30)
    model_version = Column(String(50), default="stub-0.1")  # Version stub-0.1
    quality = Column(String(50), default="low")  # low / high
    params_hash = Column(String(100), nullable=True)
    scenario_id = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    company = relationship("Company", back_populates="forecasts")
    days = relationship("ForecastDay", back_populates="forecast", cascade="all, delete-orphan")


class ForecastDay(Base):
    __tablename__ = "forecast_days"

    id = Column(Integer, primary_key=True, autoincrement=True)
    forecast_id = Column(String(100), ForeignKey("forecasts.id", ondelete="CASCADE"), nullable=False, index=True)
    forecast_date = Column(Date, nullable=False, index=True)
    p10 = Column(Float, nullable=False)
    p50 = Column(Float, nullable=False)
    p90 = Column(Float, nullable=False)
    prob_negative = Column(Float, default=0.0)

    forecast = relationship("Forecast", back_populates="days")


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(String(100), primary_key=True)
    company_id = Column(String(50), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    forecast_id = Column(String(100), nullable=True)
    level = Column(String(20), default="warning")  # critical | warning | info
    gap_date = Column(Date, nullable=True)
    shortfall_p10 = Column(Float, default=0.0)
    shortfall_p50 = Column(Float, default=0.0)
    probability = Column(Float, default=0.0)
    reason = Column(Text, nullable=True)
    actions = Column(JSON, nullable=True)  # List of 3 actionable steps with simulated effects
    acknowledged = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    company = relationship("Company", back_populates="alerts")


class Scenario(Base):
    __tablename__ = "scenarios"

    id = Column(String(100), primary_key=True)
    company_id = Column(String(50), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    scenario_type = Column(String(50), nullable=False)  # delayed_payment | revenue_drop | unexpected_expense | cost_increase | custom
    params = Column(JSON, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    company = relationship("Company", back_populates="scenarios")


class IntegrationSource(Base):
    """Adapter source statuses for 1C, FNS, Bank, EDO, Marketplaces, Registries"""
    __tablename__ = "integration_sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(String(50), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    adapter_name = Column(String(50), nullable=False)  # 1c_enterprise, fns_nalog, bank_centroinvest, edo_diadoc, ofd_cashdesk, marketplaces, fedresurs_registry
    display_name = Column(String(255), nullable=False)
    description = Column(String(500), nullable=True)
    status = Column(String(50), default="mock")  # active | mock | syncing | error
    last_sync_at = Column(DateTime, nullable=True)
    events_added = Column(Integer, default=0)
    config = Column(JSON, default=dict)
    last_payload = Column(JSON, nullable=True)  # Snapshot of received data for transparency

    company = relationship("Company", back_populates="integrations")


class AuditLog(Base):
    """Security audit log - NO PII, NO amounts, NO counterparties, only IDs and actions"""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), nullable=True)
    company_id = Column(String(50), nullable=True)
    action = Column(String(100), nullable=False)
    object_id = Column(String(100), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)


class VerificationCode(Base):
    """One-time password (OTP) verification codes sent to email"""
    __tablename__ = "verification_codes"

    id = Column(String(50), primary_key=True, index=True)
    email = Column(String(255), index=True, nullable=False)
    code = Column(String(10), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    is_used = Column(Boolean, default=False)
    attempts = Column(Integer, default=0)


class Counterparty(Base):
    """Counterparty registry for company with FNS risk analysis (nalogbi + check from api-fns.ru)"""
    __tablename__ = "counterparties"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(String(50), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    inn = Column(String(20), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    role = Column(String(50), default="payer")  # 'payer' (дебитор/покупатель), 'supplier' (поставщик), 'both'
    turnover = Column(Float, default=0.0)
    inflow_sum = Column(Float, default=0.0)
    outflow_sum = Column(Float, default=0.0)
    ops_count = Column(Integer, default=0)
    last_op_date = Column(Date, nullable=True)

    # FNS check results (nalogbi + check)
    last_checked_at = Column(DateTime, nullable=True)
    has_blocks = Column(Boolean, default=False)  # nalogbi: приостановление операций по счетам
    blocks_count = Column(Integer, default=0)
    blocks_info = Column(JSON, nullable=True)

    risk_level = Column(String(20), default="unknown")  # 'green', 'yellow', 'red', 'unknown'
    reliability_score = Column(Integer, default=100)  # 0..100
    negative_factors = Column(JSON, nullable=True)  # list of strings
    positive_factors = Column(JSON, nullable=True)  # list of strings
    check_summary = Column(Text, nullable=True)
    recommended_action = Column(String(500), nullable=True)

    include_in_forecast = Column(Boolean, default=True)  # Галочка «Учитывать проверку в итоговом графике»
    created_at = Column(DateTime, default=datetime.utcnow)

    company = relationship("Company", back_populates="counterparties")

    __table_args__ = (
        Index("idx_cp_company_inn", "company_id", "inn", unique=True),
    )


class StatementUploadHistory(Base):
    __tablename__ = "statement_upload_history"

    id = Column(String(50), primary_key=True)
    company_id = Column(String(50), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    file_size_bytes = Column(Integer, default=0)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String(50), default="success")  # success | error
    operations_count = Column(Integer, default=0)
    slots_detected = Column(Integer, default=0)
    last_balance = Column(Float, default=0.0)
    data_quality_score = Column(Float, default=100.0)
    execution_time_sec = Column(Float, default=0.0)

    company = relationship("Company")



