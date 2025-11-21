# Database configuration and session management

from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from ..core.config import settings
from typing import Annotated, Any, Dict, Optional
from fastapi import Depends
from sqlalchemy import Column, JSON, BigInteger

DATABASE_URL = settings.database_url
engine = create_async_engine(DATABASE_URL, echo=False)

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





class Sverka(SQLModel, table=True):
    __tablename__ = "sverka"
    id: int | None = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="users.id", index=True)
    vacancy_id: str = Field(default=None)
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


class UserCandidate(SQLModel, table=True):
    __tablename__ = "user_candidate"
    id: int | None = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="users.id", index=True)

    user: Optional["User"] = Relationship(back_populates="user_candidates")


class UserNotification(SQLModel, table=True):
    __tablename__ = 'user_notitfication'
    id: int | None = Field(default=None, primary_key=True)
    notification : str = Field(default=None)
    url : str = Field(default=None)
    user_id : Optional[int] = Field(default=None, foreign_key="users.id", index=True)


    user: Optional["User"] = Relationship(back_populates="user_notifications")

class User(SQLModel, table=True):
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    hashed_password: str = Field(default=None)
    work_telegram: Optional[str] = Field(default=None)
    work_email: Optional[str] = Field(default=None)
    work_telegram_session_name: Optional[str] = Field(default=None)
    work_email_app_pass: Optional[str] = Field(default=None)
    sverkas: list[Sverka] = Relationship(back_populates="user")
    user_comunications: list[UserComunication] = Relationship(back_populates="user")
    user_candidates: list[UserCandidate] = Relationship(back_populates="user")
    user_notifications: list[UserNotification] = Relationship(back_populates="user")




    
async def get_db():
    async with AsyncSession(engine) as session:
        yield session


async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


SessionDep = Annotated[AsyncSession, Depends(get_db)]