from fastapi import APIRouter , Request, Query, Depends
from app.models.vacancy import VacancyIn
from fastapi import Body
from app.database.vacancy_db import VacancyRepository
from app.database.dropdown_db import DropdownOptions
from fastapi.templating import Jinja2Templates
from pathlib import Path
from typing import Optional
from app.core.utils import parse_list
from app.core.current_user import get_current_user_from_cookie
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi import HTTPException
import re

vacancy_repository = VacancyRepository()
dropdown_options = DropdownOptions()

# BASE_DIR = app/
templates = Jinja2Templates(directory="templates")
router = APIRouter()



@router.get("/vacancy")
async def vac_main(request: Request, current_user=Depends(get_current_user_from_cookie)):
    if not current_user:
        return RedirectResponse("/auth/login", status_code=303)
    # только шаблон — без выборки из БД
    return templates.TemplateResponse(
        "vacancy/vacancy_start.html",
        {"request": request, "user_email": current_user.email, 'user_id': current_user.id}
    )


def get_repo() -> VacancyRepository:
    return VacancyRepository()

@router.get("/vacancies/search")
async def search_vacancies(
    work_format: Optional[str] = Query(None),
    employment_type: Optional[str] = Query(None),
    english_level: Optional[str] = Query(None),
    company_type: Optional[str] = Query(None),
    grade: Optional[str] = Query(None),
    specializations: Optional[str] = Query(None),
    skills: Optional[str] = Query(None),
    domains: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    manager: Optional[str] = Query(None),
    customer: Optional[str] = Query(None),
    title: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    repo: VacancyRepository = Depends(get_repo),
):
    """
    Поиск вакансий с фильтрами.
    Фронт шлёт:
    - work_format=remote,office
    - grade=middle,senior
    - specializations=Backend,Data Science
    и т.д.
    """
    return await repo.search_vacancies(
        work_format=work_format,
        employment_type=employment_type,
        english_level=english_level,
        company_type=company_type,
        grade=grade,
        specializations=specializations,
        skills=skills,
        domains=domains,
        location=location,
        manager=manager,
        customer=customer,
        title=title,
        page=page,
        page_size=page_size,
    )

def split_csv(s: str | None) -> list[str]:
    if not s:
        return []
    # режем по запятой / ; / | / /
    parts = re.split(r"[;,/|]", s)
    return [p.strip() for p in parts if p.strip()]


@router.get("/vacancy/{vacancy_id}", response_class=HTMLResponse)
async def vacancy_detail(request: Request, vacancy_id: str, current_user=Depends(get_current_user_from_cookie)):
    if not current_user:
        return RedirectResponse("/auth/login", status_code=303)
    vacancy = await vacancy_repository.get_vacancy_by_vacancy_id(vacancy_id)
    if not vacancy:
        raise HTTPException(status_code=404, detail="Vacancy not found")

    spec_list = split_csv(vacancy.specializations)
    skills_list = split_csv(vacancy.skills)
    domains_list = split_csv(vacancy.domains)

    return templates.TemplateResponse(
        "vacancy/vacancy_detail.html",
        {
            "request": request,
            "vacancy": vacancy,
            "specializations": spec_list,
            "skills": skills_list,
            "domains": domains_list,
            'user_email' : current_user.email,
            'user_id' : current_user.id
        },
    )






















@router.post("/vacancy_create")
async def vacancy_post(vacancy:list[VacancyIn] = Body(...)):
    success = await vacancy_repository.add_vacancy(vacancy)
    skill = await dropdown_options.add_skill(vacancy)
    spec = await dropdown_options.add_specialization(vacancy)
    domain = await dropdown_options.add_domain(vacancy)
    location = await dropdown_options.add_location(vacancy)
    manager = await dropdown_options.add_manager(vacancy)
    customer = await dropdown_options.add_customer(vacancy)
    if success and skill and spec and domain and location and manager and customer:
        return {"message": "Vacancy added successfully"}
    else:
        return {"message": "Failed to add vacancy"}
    
   
@router.get("/vacancies_create")
async def get_all_vacancies():
    vacancies = await vacancy_repository.get_all_vacancies()
    await dropdown_options.add_skill(vacancies)
    await dropdown_options.add_specialization(vacancies)
    await dropdown_options.add_domain(vacancies)
    c = await dropdown_options.add_location(vacancies)
    await dropdown_options.add_manager(vacancies)
    await dropdown_options.add_customer(vacancies)
    return c
