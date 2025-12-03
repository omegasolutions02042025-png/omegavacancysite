"""
Модели профилей для системы ролей пользователей.

Использует SQLModel для асинхронной работы с базой данных.
Профили связаны с основной моделью User из app.database.database через One-to-One отношения.
"""

from enum import Enum
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship, Column
from sqlalchemy import Enum as SQLEnum, JSON

# Импортируем UserRole из database.py для единообразия
# (будет использоваться в миграциях и других местах)
from app.database.database import UserRole

if TYPE_CHECKING:
    from app.database.database import User


# ============================================================================
# Enums
# ============================================================================

class Grade(str, Enum):
    """Уровень кандидата/контрактора."""
    JUNIOR = "JUNIOR"
    MIDDLE = "MIDDLE"
    SENIOR = "SENIOR"
    LEAD = "LEAD"


# ============================================================================
# Mixins
# ============================================================================

class TimestampMixin:
    """
    Миксин для добавления временных меток создания и обновления.
    
    Использует строки в формате ISO для совместимости с существующим кодом.
    Не наследуется от SQLModel, чтобы избежать конфликтов MRO.
    """
    created_at: Optional[str] = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="Дата и время создания записи (ISO format)"
    )
    updated_at: Optional[str] = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="Дата и время последнего обновления записи (ISO format)"
    )


# ============================================================================
# Candidate Profile Model
# ============================================================================

class CandidateProfile(SQLModel, TimestampMixin, table=True):
    """
    Профиль кандидата (One-to-One с User).
    
    Содержит информацию о кандидате: уровень, опыт, стек, резюме, биография.
    Связан с существующей таблицей users через user_id.
    """
    __tablename__ = "candidate_profiles_roles"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(
        foreign_key="users.id",
        unique=True,
        index=True,
        description="ID пользователя (One-to-One, ссылается на таблицу users)"
    )
    grade: Optional[Grade] = Field(
        default=None,
        sa_column=Column(SQLEnum(Grade)),
        description="Уровень кандидата (Junior/Middle/Senior/Lead)"
    )
    experience_years: Optional[int] = Field(
        default=None,
        description="Опыт работы в годах"
    )
    stack: Optional[List[str]] = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
        description="Технологический стек (JSON массив строк)"
    )
    resume_url: Optional[str] = Field(
        default=None,
        description="URL резюме кандидата"
    )
    bio: Optional[str] = Field(
        default=None,
        description="Биография/описание кандидата"
    )
    
    # Relationship
    user: Optional["User"] = Relationship(back_populates="candidate_profile")


# ============================================================================
# Recruiter Profile Model
# ============================================================================

class RecruiterProfile(SQLModel, TimestampMixin, table=True):
    """
    Профиль рекрутера (One-to-One с User).
    
    Содержит информацию о рекрутере: специализация, опыт, контакты.
    Связан с существующей таблицей users через user_id.
    """
    __tablename__ = "recruiter_profiles_roles"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(
        foreign_key="users.id",
        unique=True,
        index=True,
        description="ID пользователя (One-to-One, ссылается на таблицу users)"
    )
    specialization: Optional[str] = Field(
        default=None,
        description="Специализация рекрутера"
    )
    experience_years: Optional[int] = Field(
        default=None,
        description="Опыт работы в годах"
    )
    company: Optional[str] = Field(
        default=None,
        description="Компания рекрутера"
    )
    phone: Optional[str] = Field(
        default=None,
        description="Телефон рекрутера"
    )
    telegram: Optional[str] = Field(
        default=None,
        description="Telegram рекрутера"
    )
    linkedin: Optional[str] = Field(
        default=None,
        description="LinkedIn рекрутера"
    )
    
    # Relationship
    user: Optional["User"] = Relationship(back_populates="recruiter_profile")


# ============================================================================
# Contractor Profile Model
# ============================================================================

class ContractorProfile(SQLModel, TimestampMixin, table=True):
    """
    Профиль контрактора (One-to-One с User).
    
    Содержит информацию о контракторе: уровень, стек, ставка, доступность.
    Связан с существующей таблицей users через user_id.
    """
    __tablename__ = "contractor_profiles_roles"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(
        foreign_key="users.id",
        unique=True,
        index=True,
        description="ID пользователя (One-to-One, ссылается на таблицу users)"
    )
    grade: Optional[Grade] = Field(
        default=None,
        sa_column=Column(SQLEnum(Grade)),
        description="Уровень контрактора (Junior/Middle/Senior/Lead)"
    )
    experience_years: Optional[int] = Field(
        default=None,
        description="Опыт работы в годах"
    )
    stack: Optional[List[str]] = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
        description="Технологический стек (JSON массив строк)"
    )
    hourly_rate_usd: Optional[float] = Field(
        default=None,
        description="Почасовая ставка в USD"
    )
    is_available: bool = Field(
        default=True,
        description="Доступен ли контрактор для работы"
    )
    portfolio_url: Optional[str] = Field(
        default=None,
        description="URL портфолио контрактора"
    )
    bio: Optional[str] = Field(
        default=None,
        description="Биография/описание контрактора"
    )
    
    # Relationship
    user: Optional["User"] = Relationship(back_populates="contractor_profile")

