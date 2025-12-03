from typing import Optional, Union, List, Annotated
from fastapi import Form

from pydantic import BaseModel

from sqlmodel import SQLModel



    
class VacancyIn(BaseModel):
    vacancy_id: Optional[str] = None  # Опционально, будет сгенерирован если не указан
    title: Optional[str] = "Без названия"  # Опционально
    vacancy_text: Optional[str] = ""  # Опционально
    work_format: str
    employment_type: str
    english_level: str
    grade: str
    company_type: str
    specializations: Union[str, List[str]]  # Может быть строка или массив
    skills: Union[str, List[str]]  # Может быть строка или массив
    domains: Union[str, List[str]]  # Может быть строка или массив
    location: Union[str, List[str]]  # Может быть строка или массив
    manager_username: Optional[str] = None  # Опционально
    customer: str
    categories: Union[str, List[str]]  # Может быть строка или массив
    subcategories: Union[str, List[str]]  # Может быть строка или массив
    created_at: Optional[str] = None  # Дата создания (ISO формат), будет установлена автоматически если не указана
    salary: Optional[str] = None  # Ставка в рублях РФ
    

class MailPath(BaseModel):
    vacancy_id: str
    candidate_fullname: str

class ClarificationsMail(BaseModel):
    vacancy_id: str
    candidate_fullname: str
    tg_username: str
    clarifications: Optional[Union[str, List[str]]] = None

    @classmethod
    def as_form(
        cls,
        vacancy_id: Annotated[str, Form(...)],
        candidate_fullname: Annotated[str, Form(...)],
        tg_username: Annotated[str, Form(...)],
        clarifications: Annotated[Optional[str], Form(None)] = None,
    ):
        return cls(
            vacancy_id=vacancy_id,
            candidate_fullname=candidate_fullname,
            tg_username=tg_username,
            clarifications=clarifications,
        )
    
    

