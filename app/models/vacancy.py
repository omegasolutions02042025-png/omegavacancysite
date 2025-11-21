from typing import Optional, Union, List, Annotated
from fastapi import Form

from pydantic import BaseModel

from sqlmodel import SQLModel



    
class VacancyIn(SQLModel):
    vacancy_id: str
    title: str
    vacancy_text: str
    work_format : str
    employment_type : str
    english_level : str
    grade : str
    company_type : str
    specializations : str
    skills : str 
    domains : str 
    location : str
    manager_username : str
    customer : str
    

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
    
    

