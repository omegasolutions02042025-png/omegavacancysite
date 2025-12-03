# Database configuration and session management

from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from ..core.config import settings
from typing import Annotated, Any, Dict, Optional
from fastapi import Depends
from sqlalchemy import Column, JSON, BigInteger, UniqueConstraint, Enum as SQLEnum
from datetime import datetime
from ..models.exchange_rate import ExchangeRate
from enum import Enum

DATABASE_URL = settings.database_url
engine = create_async_engine(DATABASE_URL, echo=False)


# ============================================================================
# Enums для системы ролей
# ============================================================================

class UserRole(str, Enum):
    """Роли пользователей в системе."""
    CANDIDATE = "CANDIDATE"
    RECRUITER = "RECRUITER"
    CONTRACTOR = "CONTRACTOR"
    ADMIN = "ADMIN"

class Vacancy(SQLModel, table=True):
    __tablename__ = "vacancy"
    id: int | None = Field(default=None, primary_key=True)
    vacancy_id: str = Field(default=None, unique=True)
    title: str = Field(default=None)
    vacancy_text: str = Field(default=None)
    work_format : str = Field(default=None)
    employment_type : str = Field(default=None)
    english_level : str = Field(default=None)
    grade : str = Field(default=None)
    company_type : str = Field(default=None)
    specializations : str = Field(default=None)
    skills : str = Field(default=None)
    domains : str = Field(default=None)
    manager_username : str = Field(default=None)
    location : str = Field(default=None)
    customer : str = Field(default=None)
    categories: str | None = Field(default=None)
    subcategories: str | None = Field(default=None)
    created_at: Optional[str] = Field(default=None, index=True)  # Дата создания вакансии
    salary: Optional[str] = Field(default=None)  # Ставка в рублях РФ


class SkillDropdown(SQLModel, table=True):
    __tablename__ = "skill_dropdown"
    id: int | None = Field(default=None, primary_key=True)
    skill_name: str = Field(default=None, unique=True)

class SpecializationDropdown(SQLModel, table=True):
    __tablename__ = "specialization_dropdown"
    id: int | None = Field(default=None, primary_key=True)
    specialization_name: str = Field(default=None, unique=True)

class DomainDropdown(SQLModel, table=True):
    __tablename__ = "domain_dropdown"
    id: int | None = Field(default=None, primary_key=True)
    domain_name: str = Field(default=None, unique=True)


class LocationDropdown(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    location_name: str = Field(index=True, unique=True)

class ManagerDropdown(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    manager_name: str = Field(index=True, unique=True)

class CustomerDropdown(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    customer_name: str = Field(index=True, unique=True)


class UserCustomerAccess(SQLModel, table=True):
    """
    Таблица для связи many-to-many между рекрутерами (User) и заказчиками (CustomerDropdown).
    Админ назначает доступ рекрутерам к определенным заказчикам.
    """
    __tablename__ = "user_customer_access"
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    customer_id: int = Field(foreign_key="customerdropdown.id", index=True)
    created_at: Optional[str] = Field(default_factory=lambda: datetime.now().isoformat())
    
    # Уникальная комбинация user_id + customer_id
    __table_args__ = (
        UniqueConstraint('user_id', 'customer_id', name='uq_user_customer'),
    )


class CategoryDropdown(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    category_name: str = Field(index=True, unique=True)


class SubcategoryDropdown(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    subcategory_name: str = Field(index=True, unique=True)


class Chat(SQLModel, table=True):
    __tablename__ = "chat"
    id: int | None = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="users.id", index=True)
    candidate_id: Optional[int] = Field(default=None, index=True)  # number_for_user кандидата
    candidate_fullname: str = Field(default=None, index=True)
    vacancy_id: Optional[str] = Field(default=None, index=True)
    vacancy_title: Optional[str] = Field(default=None)  # Название вакансии
    message_type: str = Field(default=None)  # 'telegram' или 'email'
    sender: str = Field(default=None)  # 'user' или 'candidate'
    message_text: str = Field(default=None)
    timestamp: Optional[str] = Field(default=None)
    is_read: bool = Field(default=False)
    
    # Поля для файлов/медиа
    has_media: bool = Field(default=False)  # Есть ли медиа файл
    media_type: Optional[str] = Field(default=None)  # 'photo', 'document', 'video', 'audio'
    media_path: Optional[str] = Field(default=None)  # Путь к файлу на сервере
    media_filename: Optional[str] = Field(default=None)  # Оригинальное имя файла
    
    user: Optional["User"] = Relationship(back_populates="chats")



class Sverka(SQLModel, table=True):
    __tablename__ = "sverka"
    id: int | None = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="users.id", index=True)
    vacancy_id: str = Field(default=None)
    slug : str = Field(default=None)
    sverka_json: Dict[str, Any] = Field(sa_column=Column(JSON), default=None)
    candidate_fullname: str = Field(default=None)
    
    user: Optional["User"] = Relationship(back_populates="sverkas")

    

class UserComunication(SQLModel, table=True):
    __tablename__ = "user_comunication"
    id: int | None = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="users.id", index=True)
    telegram_user_id: Optional[int] = Field(
        sa_column=Column(BigInteger, index=True, nullable=True)
    )
    email_user : Optional[str] = Field(default=None)
    vacancy_id : Optional[str] = Field(default=None)
    candidate_fullname : Optional[str] = Field(default=None) 

    user: Optional["User"] = Relationship(back_populates="user_comunications")


class TelegramDialogStatus(SQLModel, table=True):
    """Таблица для отслеживания статуса Telegram диалогов (добавлен/скрыт)"""
    __tablename__ = "telegram_dialog_status"
    id: int | None = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="users.id", index=True)
    telegram_chat_id: Optional[int] = Field(
        sa_column=Column(BigInteger, index=True, nullable=False)
    )
    status: str = Field(default="hidden")  # 'added' или 'hidden'
    created_at: Optional[str] = Field(default=None)
    
    user: Optional["User"] = Relationship(back_populates="telegram_dialog_statuses")




class UserNotification(SQLModel, table=True):
    __tablename__ = 'user_notitfication'
    id: int | None = Field(default=None, primary_key=True)
    notification : str = Field(default=None)
    url : str = Field(default=None)
    user_id : Optional[int] = Field(default=None, foreign_key="users.id", index=True)


    user: Optional["User"] = Relationship(back_populates="user_notifications")




class CandidateProfileDB(SQLModel, table=True):
    """
    Таблица с профилями кандидатов, куда мы сохраняем распарсенный GPT-профиль.

    — Простые поля (строки, числа) лежат как обычные колонки.
    — experience / education / courses / projects храним как JSON-массивы dict'ов.
    """

    __tablename__ = "candidate_profiles"

    # системные поля
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(
        default=None,
        foreign_key="users.id",
        index=True,
        description="ID пользователя / рекрутера, которому принадлежит кандидат",
    )
    number_for_user: Optional[int] = Field(
        default=None,
        index=True,
        description="Порядковый номер кандидата внутри одного пользователя",
    )

    # personal
    first_name: Optional[str] = Field(default=None, index=True)
    last_name: Optional[str] = Field(default=None, index=True)
    middle_name: Optional[str] = Field(default=None, index=True)
    title: Optional[str] = Field(default=None, index=True)
    email: Optional[str] = Field(default=None, index=True)
    telegram: Optional[str] = Field(default=None, index=True)
    phone: Optional[str] = Field(default=None)
    linkedin: Optional[str] = Field(default=None)
    github: Optional[str] = Field(default=None)
    portfolio: Optional[str] = Field(default=None)
    about: Optional[str] = Field(default=None)
    photo_path: Optional[str] = Field(default=None)  # Путь к фото кандидата

    # main
    salary_usd: Optional[float] = Field(
        default=None,
        description="Ожидания по зарплате в USD (если удалось достать)",
    )
    currencies: Optional[str] = Field(
        default=None,
        description='Список валют, например: "RUB, USD, EUR"',
    )
    
    # Поля для модуля валют и ставок
    base_rate_amount: Optional[float] = Field(
        default=None,
        description="Основная ставка кандидата (числовое значение)",
    )
    base_rate_currency: Optional[str] = Field(
        default="RUB",
        description="Валюта основной ставки (RUB, USD, EUR, BYN)",
    )
    rate_type: Optional[str] = Field(
        default="monthly",
        description="Тип ставки: hourly, monthly, yearly",
    )
    
    # Кэшированные значения в других валютах
    rate_rub: Optional[float] = Field(default=None, description="Ставка в рублях")
    rate_usd: Optional[float] = Field(default=None, description="Ставка в долларах")
    rate_eur: Optional[float] = Field(default=None, description="Ставка в евро")
    rate_byn: Optional[float] = Field(default=None, description="Ставка в белорусских рублях")
    
    # Метаданные пересчета
    rates_calculated_at: Optional[str] = Field(
        default=None,
        description="Дата и время последнего пересчета ставок",
    )
    exchange_rate_snapshot_id: Optional[int] = Field(
        default=None,
        description="ID среза курса, использованного для расчета",
    )
    grade: Optional[str] = Field(default=None, description="Junior/Middle/Senior/Lead и т.п.")
    work_format: Optional[str] = Field(
        default=None,
        description="Онлайн/офлайн/гибрид и т.п.",
    )
    employment_type: Optional[str] = Field(
        default=None,
        description="Full-time/Part-time/Contract",
    )
    company_types: Optional[str] = Field(
        default=None,
        description='Типы компаний, напр.: "Стартап, Продуктовая компания"',
    )
    specializations: Optional[str] = Field(
        default=None,
        description='Напр.: "Backend_dev, Full-stack_dev, Data Engineer"',
    )
    skills: Optional[str] = Field(
        default=None,
        description="Строка с основными навыками через запятую",
    )

    # location
    city: Optional[str] = Field(default=None, index=True)
    timezone: Optional[str] = Field(default=None)
    regions: Optional[str] = Field(
        default=None,
        description='Регионы, напр.: "Европа, США"',
    )
    countries: Optional[str] = Field(
        default=None,
        description='Страны, напр.: "Германия, Нидерланды"',
    )
    relocation: Optional[str] = Field(
        default=None,
        description="Готовность/условия релокации (Yes/No/Discuss/страны)",
    )
    # сложные поля храним как JSON (список объектов)
    experience: Optional[list[Dict[str, Any]]] = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
        description="Список мест работы: [{'title', 'company', 'location', 'period', 'description'}, ...]",
    )
    education: Optional[list[Dict[str, Any]]] = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
        description="Список образований: [{'university', 'degree', 'period'}, ...]",
    )
    courses: Optional[list[Dict[str, Any]]] = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
        description="Список курсов/сертификатов: [{'name', 'organization', 'year'}, ...]",
    )
    projects: Optional[list[Dict[str, Any]]] = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
        description="Список проектов: [{'name', 'description'}, ...]",
    )

    # только английский
    english_level: Optional[str] = Field(
        default=None,
        description="Уровень английского A1–C2 или None",
    )

    # связь с пользователем
    user: Optional["User"] = Relationship(back_populates="user_candidates")


class RegistrationRequest(SQLModel, table=True):
    """Заявки на регистрацию аккаунта"""
    __tablename__ = "registration_requests"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    password: str = Field(default=None)  # Храним в открытом виде для администратора
    
    # Профиль
    first_name: Optional[str] = Field(default=None)
    last_name: Optional[str] = Field(default=None)
    middle_name: Optional[str] = Field(default=None)
    phone: Optional[str] = Field(default=None)
    specialization: Optional[str] = Field(default=None)
    experience: Optional[str] = Field(default=None)
    resume: Optional[str] = Field(default=None)

    verification_token: str = Field(default=None, index=True)
    is_email_verified: bool = Field(default=False)
    is_approved: Optional[bool] = Field(default=None)  # None=pending, True=approved, False=rejected
    approved_by_admin: Optional[int] = Field(default=None, foreign_key="admins.id")
    created_at: Optional[str] = Field(default=None)
    verified_at: Optional[str] = Field(default=None)
    processed_at: Optional[str] = Field(default=None)
    # Поля согласия на обработку персональных данных
    pd_consent: bool = Field(default=False, description="Согласие на обработку персональных данных")
    pd_consent_at: Optional[str] = Field(default=None, description="Дата и время предоставления согласия")
    pd_consent_email: Optional[str] = Field(default=None, description="Email, с которого было предоставлено согласие")
    pd_consent_ip: Optional[str] = Field(default=None, description="IP-адрес, с которого было предоставлено согласие")


class PasswordResetToken(SQLModel, table=True):
    """Токены для восстановления пароля"""
    __tablename__ = "password_reset_tokens"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    token: str = Field(index=True, unique=True)
    created_at: Optional[str] = Field(default=None)
    expires_at: Optional[str] = Field(default=None)  # Время истечения токена
    used: bool = Field(default=False)  # Использован ли токен


class Admin(SQLModel, table=True):
    __tablename__ = "admins"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    hashed_password: str = Field(default=None)
    photo_path: Optional[str] = Field(default=None)  # Путь к фото администратора
    created_at: Optional[str] = Field(default=None)


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    password: str = Field(default=None)  # Храним в открытом виде для администратора
    # Профиль рекрутера
    first_name: Optional[str] = Field(default=None, description="Имя рекрутера")
    last_name: Optional[str] = Field(default=None, description="Фамилия рекрутера")
    middle_name: Optional[str] = Field(default=None, description="Отчество рекрутера")
    phone: Optional[str] = Field(default=None, description="Телефон рекрутера")
    work_telegram: Optional[str] = Field(default=None, description="Telegram username рекрутера")
    work_email: Optional[str] = Field(default=None)
    work_telegram_session_name: Optional[str] = Field(default=None)
    work_email_app_pass: Optional[str] = Field(default=None)
    photo_path: Optional[str] = Field(default=None)  # Путь к фото рекрутера
    experience: Optional[str] = Field(default=None, description="Опыт работы рекрутера")
    specialization: Optional[str] = Field(default=None, description="Специализация рекрутера")
    resume: Optional[str] = Field(default=None, description="Резюме рекрутера (текст или путь к файлу)")
    is_archived: bool = Field(default=False, description="Статус архива: пользователи в архиве не могут входить в систему")
    archived_at: Optional[str] = Field(default=None, description="Дата и время перевода в архив")
    archived_by_admin: Optional[int] = Field(default=None, foreign_key="admins.id", description="ID администратора, который перевел в архив")
    password_changed_at: Optional[str] = Field(default=None, description="Дата и время последней смены пароля")
    # Поля согласия на обработку персональных данных
    pd_consent: bool = Field(default=False, description="Согласие на обработку персональных данных")
    pd_consent_at: Optional[str] = Field(default=None, description="Дата и время предоставления согласия")
    pd_consent_email: Optional[str] = Field(default=None, description="Email, с которого было предоставлено согласие")
    pd_consent_ip: Optional[str] = Field(default=None, description="IP-адрес, с которого было предоставлено согласие")
    created_by_admin: Optional[int] = Field(default=None, foreign_key="admins.id")
    created_at: Optional[str] = Field(default=None)
    # Поле роли пользователя (добавлено для поддержки новых ролей)
    role: Optional[UserRole] = Field(
        default=UserRole.RECRUITER,
        sa_column=Column(SQLEnum(UserRole), nullable=True),
        description="Роль пользователя в системе (CANDIDATE, RECRUITER, CONTRACTOR, ADMIN)"
    )
    sverkas: list[Sverka] = Relationship(back_populates="user")
    user_comunications: list[UserComunication] = Relationship(back_populates="user")
    user_notifications: list[UserNotification] = Relationship(back_populates="user")
    user_candidates: list[CandidateProfileDB] = Relationship(back_populates="user")
    chats: list[Chat] = Relationship(back_populates="user")
    telegram_dialog_statuses: list[TelegramDialogStatus] = Relationship(back_populates="user")
    # Relationships для профилей ролей (One-to-One)
    candidate_profile: Optional["CandidateProfile"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"uselist": False}
    )
    recruiter_profile: Optional["RecruiterProfile"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"uselist": False}
    )
    contractor_profile: Optional["ContractorProfile"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"uselist": False}
    )




    
async def get_db():
    async with AsyncSession(engine) as session:
        yield session


async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


SessionDep = Annotated[AsyncSession, Depends(get_db)]


# ============================================================================
# Импорт моделей профилей для регистрации в SQLModel.metadata
# (нужно для Alembic autogenerate)
# ============================================================================
# Импортируем модели профилей после определения User, чтобы избежать циклических импортов
from ..models.users import CandidateProfile, RecruiterProfile, ContractorProfile, Grade  # noqa: E402, F401