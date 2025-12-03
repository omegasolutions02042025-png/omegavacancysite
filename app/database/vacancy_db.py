from __future__ import annotations

import json
import re
from typing import Iterable, Dict, Any, Optional, List
from datetime import datetime, timedelta

from sqlalchemy import select, func, or_, desc, asc, cast
from sqlalchemy.types import Numeric
from sqlalchemy.ext.asyncio import AsyncSession

from .database import Vacancy, engine, Sverka
from ..models.vacancy import VacancyIn


class VacancyRepository:
    def __init__(self):
        self.engine = engine

    # ========= GET VACANCY BY ID =========
    
    async def get_vacancy_by_id(self, vacancy_id: str) -> Optional[Vacancy]:
        """Получить вакансию по ID"""
        async with AsyncSession(self.engine) as session:
            stmt = select(Vacancy).where(Vacancy.vacancy_id == vacancy_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

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
        import uuid
        from datetime import datetime
        
        objs: list[Vacancy] = []
        for r in rows:
            d = r.model_dump()
            
            # Генерируем vacancy_id если не указан
            if not d.get('vacancy_id'):
                d['vacancy_id'] = f"VAC-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8]}"
            
            # Устанавливаем дату создания если не указана
            if not d.get('created_at'):
                d['created_at'] = datetime.now().isoformat()
            
            # Преобразуем списки в строки (через запятую)
            for field in ['specializations', 'skills', 'domains', 'location', 'categories', 'subcategories']:
                if field in d and isinstance(d[field], list):
                    d[field] = ', '.join(str(item) for item in d[field] if item)
            
           
            
            objs.append(Vacancy(**d))

        async with AsyncSession(self.engine) as session:
            ids = [o.vacancy_id for o in objs]

            result = await session.execute(
                select(Vacancy.vacancy_id).where(Vacancy.vacancy_id.in_(ids))
            )
            existing = set[Any](result.scalars().all())

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

    async def get_last_sverka_by_vacancy_and_candidate_and_user_id(
        self,
        vacancy_id: str,
        candidate_fullname: str,
        user_id: int,
    ) -> Sverka | None:
        """
        Получить последнюю (самую свежую) сверку по вакансии, кандидату и пользователю.
        """
        async with AsyncSession(self.engine) as session:
            result = await session.execute(
                select(Sverka).where(
                    Sverka.vacancy_id == vacancy_id,
                    Sverka.candidate_fullname == candidate_fullname,
                    Sverka.user_id == user_id,
                ).order_by(Sverka.id.desc())
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
        categories: Optional[str] = None,      # "Infrastructure,Support"
        subcategories: Optional[str] = None,   # "Cloud,Kafka"
        location: Optional[str] = None,        # "РФ" или "РФ, РБ"
        manager: Optional[str] = None,         # имя/username менеджера
        customer: Optional[str] = None,        # заказчик/клиент
        title: Optional[str] = None,           # поисковая строка по названию
        days_ago: Optional[int] = None,       # Фильтр по дате: вакансии за последние N дней (1, 3, 7, 14, 21)
        sort_by: Optional[str] = None,         # Сортировка: "newest", "date_desc", "date_asc", "salary_desc", "salary_asc"
        filter_by: Optional[str] = None,      # Дополнительный фильтр: "with_salary", "recent_week", "recent_month"
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """
        Все фильтры между собой — AND.
        Внутри одного поля (несколько спецов/скиллов/доменов) — OR.
        Поля specializations / skills / domains / location в БД — обычные строки.
        
        Args:
            days_ago: Фильтр по дате создания (1, 3, 7, 14, 21 дней назад)
            sort_by: Тип сортировки - "newest" (новые сначала), "salary_desc" (ставка по убыванию), "salary_asc" (ставка по возрастанию)
        """

        if page < 1:
            page = 1
        if page_size < 1:
            page_size = 20

        offset = (page - 1) * page_size

        # Разбиваем все параметры, которые могут содержать несколько значений
        work_format_list = self._csv_to_list(work_format)
        employment_type_list = self._csv_to_list(employment_type)
        english_level_list = self._csv_to_list(english_level)
        company_type_list = self._csv_to_list(company_type)
        grade_list   = self._csv_to_list(grade)
        spec_list    = self._csv_to_list(specializations)
        skills_list  = self._csv_to_list(skills)
        domains_list = self._csv_to_list(domains)
        categories_list = self._csv_to_list(categories)
        subcategories_list = self._csv_to_list(subcategories)

        async with AsyncSession(self.engine) as session:
            q = select(Vacancy)

            # ===== фильтр по дате создания =====
            if days_ago and days_ago > 0:
                cutoff_date = datetime.now() - timedelta(days=days_ago)
                cutoff_iso = cutoff_date.isoformat()
                # Фильтруем вакансии, созданные после cutoff_date (исключаем NULL)
                q = q.where(
                    Vacancy.created_at.is_not(None),
                    Vacancy.created_at >= cutoff_iso
                )

            # ===== простые строковые поля с множественным выбором (OR внутри, AND между) =====
            if work_format_list:
                work_format_conds = [
                    func.lower(Vacancy.work_format) == wf.lower().strip()
                    for wf in work_format_list
                ]
                q = q.where(or_(*work_format_conds))

            if employment_type_list:
                employment_conds = [
                    func.lower(Vacancy.employment_type) == et.lower().strip()
                    for et in employment_type_list
                ]
                q = q.where(or_(*employment_conds))

            if english_level_list:
                english_conds = [
                    func.lower(Vacancy.english_level) == el.lower().strip()
                    for el in english_level_list
                ]
                q = q.where(or_(*english_conds))

            if company_type_list:
                company_conds = [
                    func.lower(Vacancy.company_type) == ct.lower().strip()
                    for ct in company_type_list
                ]
                q = q.where(or_(*company_conds))

            if grade_list:
                grade_conds = [
                    func.lower(Vacancy.grade) == g.lower().strip()
                    for g in grade_list
                ]
                q = q.where(or_(*grade_conds))

            # ===== location / manager / customer =====

            if location:
                # location может быть списком "РФ, РБ"
                # В БД location - строка, например "РФ, Москва"
                # Нужно найти любую из выбранных локаций в строке БД
                loc_list = self._csv_to_list(location)
                if loc_list:
                    loc_conds = []
                    for loc in loc_list:
                         loc_conds.append(
                            func.lower(Vacancy.location).ilike(f"%{loc.lower().strip()}%")
                         )
                    q = q.where(or_(*loc_conds))

            if manager:
                # manager может быть списком
                mgr_list = self._csv_to_list(manager)
                if mgr_list:
                    mgr_conds = []
                    # Проверяем оба поля: manager_username и manager_name
                    has_username = hasattr(Vacancy, "manager_username")
                    has_name = hasattr(Vacancy, "manager_name")
                    
                    for mgr in mgr_list:
                        mgr_val = mgr.lower().strip()
                        if has_username:
                            mgr_conds.append(func.lower(Vacancy.manager_username) == mgr_val)
                        if has_name:
                            mgr_conds.append(func.lower(Vacancy.manager_name) == mgr_val)
                            
                    if mgr_conds:
                        q = q.where(or_(*mgr_conds))

            if customer:
                # customer может быть списком
                cust_list = self._csv_to_list(customer)
                if cust_list and hasattr(Vacancy, "customer"):
                     cust_conds = [
                        func.lower(Vacancy.customer) == c.lower().strip()
                        for c in cust_list
                     ]
                     q = q.where(or_(*cust_conds))

            # ===== поиск по title =====
            if title:
                t = title.lower().strip()
                q = q.where(
                    func.lower(Vacancy.title).ilike(f"%{t}%")
                )

            # ===== дополнительный фильтр filter_by =====
            if filter_by == "with_salary":
                # Только вакансии со ставкой (salary не пустое и не NULL)
                q = q.where(
                    Vacancy.salary.is_not(None),
                    Vacancy.salary != ''
                )

            # ===== строковые "списки": specializations / skills / domains =====
            # Сначала ищем полное слово (с разделителями), если не найдено - ищем по части слова

            if spec_list:
                spec_conds = []
                for sp in spec_list:
                    sp_lower = sp.lower().strip()
                    if not sp_lower:
                        continue
                    # Экранируем специальные символы для регулярного выражения PostgreSQL
                    sp_escaped = re.escape(sp_lower)
                    # Ищем полное слово: в начале строки, после разделителя, или в конце строки
                    # Разделители: запятая, точка с запятой, слэш, вертикальная черта, пробел
                    # В PostgreSQL регулярные выражения используют POSIX синтаксис
                    # Паттерн: начало строки ИЛИ разделитель, затем слово, затем разделитель ИЛИ конец строки
                    # Используем \m и \M для границ слов в PostgreSQL (начало и конец слова)
                    # Или используем явные разделители
                    full_word_pattern = f"(^|[\\s,;/|]){sp_escaped}([\\s,;/|]|$)"
                    # Сначала пробуем найти полное слово, если не найдено - ищем подстроку
                    # Используем case-insensitive поиск через ~*
                    spec_conds.append(
                        or_(
                            func.lower(Vacancy.specializations).op('~')(full_word_pattern),
                            func.lower(Vacancy.specializations).ilike(f"%{sp_lower}%")
                        )
                    )
                if spec_conds:
                    q = q.where(or_(*spec_conds))

            if skills_list:
                skill_conds = []
                for sk in skills_list:
                    sk_lower = sk.lower().strip()
                    if not sk_lower:
                        continue
                    # Экранируем специальные символы для регулярного выражения PostgreSQL
                    sk_escaped = re.escape(sk_lower)
                    # Ищем полное слово: в начале строки, после разделителя, или в конце строки
                    # Разделители: запятая, точка с запятой, слэш, вертикальная черта, пробел
                    # В PostgreSQL регулярные выражения используют POSIX синтаксис
                    # Паттерн: начало строки ИЛИ разделитель, затем слово, затем разделитель ИЛИ конец строки
                    full_word_pattern = f"(^|[\\s,;/|]){sk_escaped}([\\s,;/|]|$)"
                    # Сначала пробуем найти полное слово, если не найдено - ищем подстроку
                    skill_conds.append(
                        or_(
                            func.lower(Vacancy.skills).op('~')(full_word_pattern),
                            func.lower(Vacancy.skills).ilike(f"%{sk_lower}%")
                        )
                    )
                if skill_conds:
                    q = q.where(or_(*skill_conds))

            if domains_list:
                domain_conds = [
                    func.lower(Vacancy.domains).ilike(f"%{dm.lower()}%")
                    for dm in domains_list
                ]
                q = q.where(or_(*domain_conds))

            if categories_list:
                category_conds = [
                    func.lower(Vacancy.categories).ilike(f"%{cat.lower()}%")
                    for cat in categories_list
                ]
                q = q.where(or_(*category_conds))

            if subcategories_list:
                subcategory_conds = [
                    func.lower(Vacancy.subcategories).ilike(f"%{sub.lower()}%")
                    for sub in subcategories_list
                ]
                q = q.where(or_(*subcategory_conds))

            # ===== total с учётом всех фильтров =====
            total = await session.scalar(
                select(func.count()).select_from(q.subquery())
            )
            total = total or 0

            # ===== сортировка =====
            if sort_by == "newest":
                # Сортировка по новизне (новые сначала)
                # Вакансии без даты идут в конец
                q = q.order_by(desc(Vacancy.created_at).nulls_last())
            elif sort_by == "date_desc":
                # Сортировка по дате по убыванию (новые сначала)
                q = q.order_by(desc(Vacancy.created_at).nulls_last())
            elif sort_by == "date_asc":
                # Сортировка по дате по возрастанию (старые сначала)
                q = q.order_by(asc(Vacancy.created_at).nulls_last())
            elif sort_by == "salary_desc":
                # Сортировка по ставке по убыванию (высокие ставки сначала)
                # Сначала вакансии с указанной ставкой, потом без ставки
                # Преобразуем строку salary в число для сортировки (убираем все нецифровые символы кроме точки и запятой)
                # Используем regexp_replace для очистки строки перед преобразованием
                # NULLIF обрабатывает случай, когда после regexp_replace остается пустая строка, заменяем на '0'
                cleaned_salary = func.regexp_replace(
                    func.coalesce(Vacancy.salary, '0'),
                    r'[^\d.,]', '', 'g'
                )
                # Заменяем пустую строку на '0' перед преобразованием в число
                salary_expr = cast(
                    func.coalesce(func.nullif(cleaned_salary, ''), '0'),
                    Numeric
                )
                q = q.order_by(desc(salary_expr).nulls_last())
            elif sort_by == "salary_asc":
                # Сортировка по ставке по возрастанию (низкие ставки сначала)
                # Сначала вакансии с указанной ставкой, потом без ставки
                cleaned_salary = func.regexp_replace(
                    func.coalesce(Vacancy.salary, '0'),
                    r'[^\d.,]', '', 'g'
                )
                # Заменяем пустую строку на '0' перед преобразованием в число
                salary_expr = cast(
                    func.coalesce(func.nullif(cleaned_salary, ''), '0'),
                    Numeric
                )
                q = q.order_by(asc(salary_expr).nulls_last())
            else:
                # По умолчанию - по новизне
                q = q.order_by(desc(Vacancy.created_at).nulls_last())

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
                    "categories": self._split_values(getattr(v, "categories", None)),
                    "subcategories": self._split_values(getattr(v, "subcategories", None)),
                    "location": self._split_values(getattr(v, "location", None)),
                    "manager": getattr(v, "manager_username", None) or getattr(v, "manager_name", None),
                    "customer": getattr(v, "customer", None),
                    "created_at": getattr(v, "created_at", None),
                    "salary": getattr(v, "salary", None),
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

    async def update_sverka_slug(self, sverka_id: int, slug: str) -> bool:
        """Обновить slug для сверки по ID."""
        async with AsyncSession(self.engine) as session:
            result = await session.execute(
                select(Sverka).where(Sverka.id == sverka_id)
            )
            sverka = result.scalars().first()
            if sverka:
                sverka.slug = slug
                await session.commit()
                return True
            return False

    async def get_sverkas_by_candidate_fullname_and_user_id(
        self, 
        user_id: int, 
        candidate_fullname: str
    ) -> list[Sverka]:
        """
        Получить все сверки для конкретного кандидата по его полному имени.
        
        Args:
            user_id: ID пользователя (рекрутера)
            candidate_fullname: Полное имя кандидата
            
        Returns:
            list[Sverka]: Список всех сверок для этого кандидата
        """
        async with AsyncSession(self.engine) as session:
            result = await session.execute(
                select(Sverka).where(
                    Sverka.user_id == user_id,
                    Sverka.candidate_fullname == candidate_fullname,
                ).order_by(Sverka.id.desc())
            )
            return list(result.scalars().all())