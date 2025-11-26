from typing import Optional, List
from pydantic import BaseModel, field_validator

# эти у тебя уже есть — оставляю для целостности
class ExperienceItem(BaseModel):
    title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    period: Optional[str] = None
    description: Optional[str] = None


class EducationItem(BaseModel):
    university: Optional[str] = None
    degree: Optional[str] = None
    period: Optional[str] = None



class CourseItem(BaseModel):
    name: Optional[str] = None
    organization: Optional[str] = None
    year: Optional[str] = None


class ProjectItem(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


# --- Блоки, которые приходят в personal / main / location ---

class PersonalBlock(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    middle_name: Optional[str] = None
    title: Optional[str] = None
    email: Optional[str] = None
    telegram: Optional[str] = None
    phone: Optional[str] = None
    linkedin: Optional[str] = None
    github: Optional[str] = None
    portfolio: Optional[str] = None
    about: Optional[str] = None


class MainBlock(BaseModel):
    salary_usd: Optional[float] = None
    currencies: Optional[str] = None
    grade: Optional[str] = None
    work_format: Optional[str] = None
    employment_type: Optional[str] = None
    company_types: Optional[str] = None
    specializations: Optional[str] = None
    skills: Optional[str] = None


class LocationBlock(BaseModel):
    city: Optional[str] = None
    timezone: Optional[str] = None
    regions: Optional[str] = None
    countries: Optional[str] = None
    relocation: Optional[str] = None


# --- Главная модель для ответа GPT ---

class GPTCandidateProfile(BaseModel):
    personal: PersonalBlock
    main: MainBlock
    location: LocationBlock

    experience: List[ExperienceItem] = []
    education: List[EducationItem] = []
    courses: List[CourseItem] = []
    projects: List[ProjectItem] = []

    english_level: Optional[str] = None

    @field_validator("experience", "education", "courses", "projects", mode="before")
    @classmethod
    def none_to_empty_list(cls, v):
        """
        GPT иногда возвращает null вместо [] для списков.
        Преобразуем None → [] чтобы валидация не падала.
        """
        if v is None:
            return []
        return v


class SverkaFromCandidateRequest(BaseModel):
    vacancy_id: str
    candidate_numbers: List[int|str]
