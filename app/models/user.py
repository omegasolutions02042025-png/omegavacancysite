# app/schemas/user.py
from pydantic import BaseModel, EmailStr, Field
from typing import Annotated

class UserBase(BaseModel):
    email: EmailStr
    


class UserCreate(UserBase):
    
    password: Annotated[str, Field(min_length=8)]
    


class UserLogin(UserBase):
    password: str




class UserProfile(UserBase):
    id: int
    hassed_password: str
    work_telegram: str | None = None
    work_telegram_session_name: str | None = None
    work_email: str | None = None
    work_email_app_pass: str | None = None

    


class UserProfileUpdate(BaseModel):
    work_telegram: str | None = None
    work_telegram_session_name: str | None = None
    work_email: str | None = None
    work_email_app_pass: str | None = None
