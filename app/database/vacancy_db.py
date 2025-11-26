from __future__ import annotations

import json
import re
from typing import Iterable, Dict, Any, Optional, List

from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from .database import Vacancy, engine, Sverka
from ..models.vacancy import VacancyIn


class VacancyRepository:
    def __init__(self):
        self.engine = engine

    # ========= UTILS =========

    @staticmethod
    def _csv_to_list(value: Optional[str]) -> list[str]:
        """
        Разобрать строку формата:
        - "DevOps, MLOps"
        - "DevOps;MLOps"
        - "DevOps / MLOps"
        -> ["DevOps", "MLOps"]
        """
        if not value:
            return []
        parts = re.split(r"[;,/|]", value)
        return [p.strip() for p in parts if p.strip()]

    @staticmethod
    def _split_values(raw: Optional[str]) -> list[str]:
        """
        Преобразует значение из БД в список:
        - 'DevOps, MLOps'
        - '["DevOps","MLOps"]'
        - '["DevOps", "MLOps"]'
        -> ["DevOps", "MLOps"]
        """
        if not raw:
            return []

        raw = raw.strip()
        # пробуем как JSON-массив
        if (raw.startswith("[") and raw.endswith("]")) or (raw.startswith('"') and raw.endswith('"')):
            try:
                data = json.loads(raw)
                if isinstance(data, list):
                    return [str(x).strip() for x in data if str(x).strip()]
            except Exception:
                # падаем в обычный разбор
                pass

        # обычная строка с разделителями
        parts = re.split(r"[;,/|]", raw)
        result: list[str] = []
        for p in parts:
            cleaned = p.strip().strip('"').strip("'")
            if cleaned:
                result.append(cleaned)
        return result

    # ========= CRUD по вакансиям / сверке =========

    async def add_vacancy(self, rows: Iterable[VacancyIn]) -> list[Vacancy]:
        objs: list[Vacancy] = []
        for r in rows:
            d = r.model_dump()
            objs.append(Vacancy(**d))

        async with AsyncSession(self.engine) as session:
            ids = [o.vacancy_id for o in objs]

            result = await session.execute(
                select(Vacancy.vacancy_id).where(Vacancy.vacancy_id.in_(ids))
            )
            existing = set(result.scalars().all())

            new_objs: list[Vacancy] = []
            for obj in objs:
                if obj.vacancy_id in existing:
                    print(f"Vacancy {obj.vacancy_id} already exists")
                    continue
                new_objs.append(obj)

            if not new_objs:
                return []

            session.add_all(new_objs)
            await session.commit()

            for obj in new_objs:
                await session.refresh(obj)

            return new_objs

    async def get_topics(self) -> list[str]:
        async with AsyncSession(self.engine) as session:
            result = await session.execute(
                select(Vacancy.topic_name)
                .distinct()
                .where(Vacancy.topic_name.is_not(None))
            )
            return result.scalars().all()

    async def get_vacancies_by_topic(self, topic_name: str) -> list[Vacancy]:
        async with AsyncSession(self.engine) as session:
            result = await session.execute(
                select(Vacancy).where(Vacancy.topic_name == topic_name)
            )
            return result.scalars().all()

    async def get_vacancy_by_vacancy_id(self, vacancy_id: str) -> Vacancy | None:
        async with AsyncSession(self.engine) as session:
            result = await session.execute(
                select(Vacancy).where(Vacancy.vacancy_id == vacancy_id)
            )
            return result.scalars().first()

    async def add_sverka(
        self,
        sverka_json: Dict[str, Any],
        slug : str,
        vacancy_id: str,
        candidate_fullname: str,
        user_id: int,
    ) -> Sverka:
        async with AsyncSession(self.engine) as session:

            sverka = Sverka(
                sverka_json=sverka_json,
                slug = slug,
                vacancy_id=vacancy_id,
                candidate_fullname=candidate_fullname,
                user_id=user_id,
            )
            session.add(sverka)
            await session.commit()
            await session.refresh(sverka)
            return sverka

    async def get_sverka_by_vacancy_and_candidate_and_user_id(
        self,
        vacancy_id: str,
        candidate_fullname: str,
        user_id: int,
    ) -> Sverka | None:
        async with AsyncSession(self.engine) as session:
            result = await session.execute(
                select(Sverka).where(
                    Sverka.vacancy_id == vacancy_id,
                    Sverka.candidate_fullname == candidate_fullname,
                    Sverka.user_id == user_id,
                )
            )
            return result.scalars().first()

    async def get_all_vacancies(self) -> list[Vacancy]:
        async with AsyncSession(self.engine) as session:
            result = await session.execute(select(Vacancy))
            return result.scalars().all()

    # ========= ПОИСК / ФИЛЬТРЫ =========

    async def search_vacancies(
        self,
        work_format: Optional[str] = None,
        employment_type: Optional[str] = None,
        english_level: Optional[str] = None,
        company_type: Optional[str] = None,
        grade: Optional[str] = None,           # "junior, middle"
        specializations: Optional[str] = None, # "Backend,Data Science"
        skills: Optional[str] = None,          # "Kubernetes,Terraform"
        domains: Optional[str] = None,         # "FinTech,GameDev"
        location: Optional[str] = None,        # "РФ" или "РФ, РБ"
        manager: Optional[str] = None,         # имя/username менеджера
        customer: Optional[str] = None,        # заказчик/клиент
        title: Optional[str] = None,           # поисковая строка по названию
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """
        Все фильтры между собой — AND.
        Внутри одного поля (несколько спецов/скиллов/доменов) — OR.
        Поля specializations / skills / domains / location в БД — обычные строки.
        """

        if page < 1:
            page = 1
        if page_size < 1:
            page_size = 20

        offset = (page - 1) * page_size

        grade_list   = self._csv_to_list(grade)
        spec_list    = self._csv_to_list(specializations)
        skills_list  = self._csv_to_list(skills)
        domains_list = self._csv_to_list(domains)

        async with AsyncSession(self.engine) as session:
            q = select(Vacancy)

            # ===== простые строковые поля (AND) =====
            if work_format:
                q = q.where(
                    func.lower(Vacancy.work_format) == work_format.lower().strip()
                )

            if employment_type:
                q = q.where(
                    func.lower(Vacancy.employment_type)
                    == employment_type.lower().strip()
                )

            if english_level:
                q = q.where(
                    func.lower(Vacancy.english_level)
                    == english_level.lower().strip()
                )

            if company_type:
                q = q.where(
                    func.lower(Vacancy.company_type)
                    == company_type.lower().strip()
                )

            if grade_list:
                q = q.where(Vacancy.grade.in_(grade_list))

            # ===== location / manager / customer =====

            if location:
                # location в БД может быть "РФ, РБ" — ищем подстроку
                q = q.where(
                    func.lower(Vacancy.location).ilike(f"%{location.lower().strip()}%")
                )

            if manager:
                # предполагаем, что в модели есть поле manager_username или manager_name
                # сначала пробуем manager_username, если его нет — не упадёт, но для чистоты можно адаптировать модель
                if hasattr(Vacancy, "manager_username"):
                    q = q.where(
                        func.lower(Vacancy.manager_username)
                        == manager.lower().strip()
                    )
                elif hasattr(Vacancy, "manager_name"):
                    q = q.where(
                        func.lower(Vacancy.manager_name)
                        == manager.lower().strip()
                    )

            if customer:
                if hasattr(Vacancy, "customer"):
                    q = q.where(
                        func.lower(Vacancy.customer)
                        == customer.lower().strip()
                    )

            # ===== поиск по title =====
            if title:
                t = title.lower().strip()
                q = q.where(
                    func.lower(Vacancy.title).ilike(f"%{t}%")
                )

            # ===== строковые "списки": specializations / skills / domains =====

            if spec_list:
                spec_conds = [
                    func.lower(Vacancy.specializations).ilike(f"%{sp.lower()}%")
                    for sp in spec_list
                ]
                q = q.where(or_(*spec_conds))

            if skills_list:
                skill_conds = [
                    func.lower(Vacancy.skills).ilike(f"%{sk.lower()}%")
                    for sk in skills_list
                ]
                q = q.where(or_(*skill_conds))

            if domains_list:
                domain_conds = [
                    func.lower(Vacancy.domains).ilike(f"%{dm.lower()}%")
                    for dm in domains_list
                ]
                q = q.where(or_(*domain_conds))

            # ===== total с учётом всех фильтров =====
            total = await session.scalar(
                select(func.count()).select_from(q.subquery())
            )
            total = total or 0

            # ===== выборка страницы =====
            q_page = q.offset(offset).limit(page_size)
            res = await session.execute(q_page)
            items: List[Vacancy] = res.scalars().all()

            def to_dict(v: Vacancy) -> dict:
                return {
                    "id": v.id,
                    "vacancy_id": v.vacancy_id,
                    "title": v.title,
                    "vacancy_text": v.vacancy_text,
                    "work_format": v.work_format,
                    "employment_type": v.employment_type,
                    "english_level": v.english_level,
                    "grade": v.grade,
                    "company_type": v.company_type,
                    "specializations": self._split_values(getattr(v, "specializations", None)),
                    "skills": self._split_values(getattr(v, "skills", None)),
                    "domains": self._split_values(getattr(v, "domains", None)),
                    "location": self._split_values(getattr(v, "location", None)),
                    "manager": getattr(v, "manager_username", None) or getattr(v, "manager_name", None),
                    "customer": getattr(v, "customer", None),
                }

            has_more = (offset + page_size) < total

            return {
                "items": [to_dict(v) for v in items],
                "total": total,
                "has_more": has_more,
            }
    async def get_sverka_history_by_user_and_vacancy(self, user_id: int, vacancy_id: str):
        async with AsyncSession(self.engine) as session:
            result = await session.execute(
                select(Sverka).where(
                    Sverka.user_id == user_id,
                    Sverka.vacancy_id == vacancy_id,
                )
            )
            return result.scalars().all()