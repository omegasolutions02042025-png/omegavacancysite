from typing import Sequence, Set, List
import json
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .database import (
    engine,
    SkillDropdown,
    SpecializationDropdown,
    DomainDropdown,
    CustomerDropdown,
    ManagerDropdown,
    LocationDropdown,
    CategoryDropdown,
    SubcategoryDropdown,
)
from ..models.vacancy import VacancyIn

# УБИРАЕМ rapidfuzz
# from rapidfuzz import fuzz, process

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


SIM_THRESHOLD = 85  # порог похожести в процентах (0–100)


class DropdownOptions:
    def __init__(self):
        self.engine = engine

    @staticmethod
    def _normalize_name(name: str) -> str:
        """
        Трим + первая буква заглавная, остальные не трогаем
        (чтобы не ломать React, Node.js и т.п.).
        """
        name = (name or "").strip()
        if not name:
            return ""
        return name[0].upper() + name[1:]

    @staticmethod
    def _find_similar(name: str, existing: Set[str]) -> str | None:
        """
        Ищем наиболее похожее значение среди existing по TF-IDF + cosine similarity.
        Если похожесть*100 >= SIM_THRESHOLD — считаем, что это дубль.
        """
        if not existing:
            return None

        # корпус: существующие значения + новое имя
        corpus = list(existing)
        target = name

        try:
            vectorizer = TfidfVectorizer()
            # последняя строка — это target
            X = vectorizer.fit_transform(corpus + [target])
        except Exception:
            # например, если всё состоит из стоп-слов и словарь пустой
            return None

        # вектор target
        target_vec = X[-1]
        existing_vecs = X[:-1]

        if existing_vecs.shape[0] == 0:
            return None

        sims = cosine_similarity(target_vec, existing_vecs)[0]  # array shape=(N,)
        if sims.size == 0:
            return None

        best_idx = sims.argmax()
        best_score = float(sims[best_idx] * 100.0)  # в процентах 0–100

        if best_score >= SIM_THRESHOLD:
            return corpus[best_idx]

        return None

    @staticmethod
    def _extract_list(raw) -> list[str]:
        """
        Приводит значение поля vacancy.skills / specializations / domains
        к списку строк.

        Поддерживает:
        — list[str]
        — JSON-строку '["Docker","Helm"]'
        — обычную строку 'Docker, Helm;Kubernetes'
        """
        if not raw:
            return []

        # уже список
        if isinstance(raw, list):
            return [str(x).strip() for x in raw if str(x).strip()]

        if isinstance(raw, str):
            s = raw.strip()
            if not s:
                return []

            # если это JSON-массив
            if s.startswith("[") and s.endswith("]"):
                try:
                    data = json.loads(s)
                    if isinstance(data, list):
                        return [str(x).strip() for x in data if str(x).strip()]
                except Exception:
                    pass

            # обычная строка — режем по разделителям
            parts = re.split(r"[;,/|]", s)
            return [p.strip() for p in parts if p.strip()]

        # всё остальное игнорируем
        return []

    # ===== SKILLS =====

    async def add_skill(self, data: Sequence[VacancyIn]) -> list[SkillDropdown]:
        async with AsyncSession(self.engine) as session:
            all_skill_names: set[str] = set()

            for vac in data:
                skill_list = self._extract_list(getattr(vac, "skills", None))
                for name in skill_list:
                    norm = self._normalize_name(name)
                    if norm:
                        all_skill_names.add(norm)

            if not all_skill_names:
                return []

            result = await session.execute(select(SkillDropdown))
            existing_objs: List[SkillDropdown] = list(result.scalars().all())
            existing_names: set[str] = {s.skill_name for s in existing_objs}

            new_skills: list[SkillDropdown] = []

            for name in all_skill_names:
                if name in existing_names:
                    continue

                similar = self._find_similar(name, existing_names)
                if similar:
                    print(f'[SKILL] "{name}" похож на "{similar}" — не добавляем новый.')
                    continue

                skill = SkillDropdown(skill_name=name)
                session.add(skill)
                new_skills.append(skill)
                existing_names.add(name)

            if new_skills:
                await session.commit()
                for s in new_skills:
                    await session.refresh(s)

            return existing_objs + new_skills

    # ===== SPECIALIZATIONS =====

    async def add_specialization(self, data: Sequence[VacancyIn]) -> list[SpecializationDropdown]:
        async with AsyncSession(self.engine) as session:
            all_spec_names: set[str] = set()

            for vac in data:
                sp_list = self._extract_list(getattr(vac, "specializations", None))
                for name in sp_list:
                    norm = self._normalize_name(name)
                    if norm:
                        all_spec_names.add(norm)

            if not all_spec_names:
                return []

            result = await session.execute(select(SpecializationDropdown))
            existing_objs: List[SpecializationDropdown] = list(result.scalars().all())
            existing_names: set[str] = {s.specialization_name for s in existing_objs}

            new_specs: list[SpecializationDropdown] = []

            for name in all_spec_names:
                if name in existing_names:
                    continue

                similar = self._find_similar(name, existing_names)
                if similar:
                    print(f'[SPEC] "{name}" похож на "{similar}" — не добавляем новый.')
                    continue

                sp = SpecializationDropdown(specialization_name=name)
                session.add(sp)
                new_specs.append(sp)
                existing_names.add(name)

            if new_specs:
                await session.commit()
                for sp in new_specs:
                    await session.refresh(sp)

            return existing_objs + new_specs

    # ===== DOMAINS =====

    async def add_domain(self, data: Sequence[VacancyIn]) -> list[DomainDropdown]:
        async with AsyncSession(self.engine) as session:
            all_domain_names: set[str] = set()

            for vac in data:
                domain_list = self._extract_list(getattr(vac, "domains", None))
                for name in domain_list:
                    norm = self._normalize_name(name)
                    if norm:
                        all_domain_names.add(norm)

            if not all_domain_names:
                return []

            result = await session.execute(select(DomainDropdown))
            existing_objs: List[DomainDropdown] = list(result.scalars().all())
            existing_names: set[str] = {d.domain_name for d in existing_objs}

            new_domains: list[DomainDropdown] = []

            for name in all_domain_names:
                if name in existing_names:
                    continue

                similar = self._find_similar(name, existing_names)
                if similar:
                    print(f'[DOMAIN] "{name}" похож на "{similar}" — не добавляем новый.')
                    continue

                d = DomainDropdown(domain_name=name)
                session.add(d)
                new_domains.append(d)
                existing_names.add(name)

            if new_domains:
                await session.commit()
                for d in new_domains:
                    await session.refresh(d)

            return existing_objs + new_domains

    # ===== CATEGORIES =====

    async def add_category(self, data: Sequence[VacancyIn]) -> list[CategoryDropdown]:
        async with AsyncSession(self.engine) as session:
            all_category_names: set[str] = set()

            for vac in data:
                cat_list = self._extract_list(getattr(vac, "categories", None))
                for name in cat_list:
                    norm = self._normalize_name(name)
                    if norm:
                        all_category_names.add(norm)

            if not all_category_names:
                return []

            result = await session.execute(select(CategoryDropdown))
            existing_objs: List[CategoryDropdown] = list(result.scalars().all())
            existing_names: set[str] = {c.category_name for c in existing_objs}

            new_categories: list[CategoryDropdown] = []

            for name in all_category_names:
                if name in existing_names:
                    continue

                similar = self._find_similar(name, existing_names)
                if similar:
                    print(f'[CATEGORY] "{name}" похож на "{similar}" — не добавляем новый.')
                    continue

                c = CategoryDropdown(category_name=name)
                session.add(c)
                new_categories.append(c)
                existing_names.add(name)

            if new_categories:
                await session.commit()
                for c in new_categories:
                    await session.refresh(c)

            return existing_objs + new_categories

    # ===== SUBCATEGORIES =====

    async def add_subcategory(self, data: Sequence[VacancyIn]) -> list[SubcategoryDropdown]:
        async with AsyncSession(self.engine) as session:
            all_subcategory_names: set[str] = set()

            for vac in data:
                subcat_list = self._extract_list(getattr(vac, "subcategories", None))
                for name in subcat_list:
                    norm = self._normalize_name(name)
                    if norm:
                        all_subcategory_names.add(norm)

            if not all_subcategory_names:
                return []

            result = await session.execute(select(SubcategoryDropdown))
            existing_objs: List[SubcategoryDropdown] = list(result.scalars().all())
            existing_names: set[str] = {s.subcategory_name for s in existing_objs}

            new_subcategories: list[SubcategoryDropdown] = []

            for name in all_subcategory_names:
                if name in existing_names:
                    continue

                similar = self._find_similar(name, existing_names)
                if similar:
                    print(f'[SUBCATEGORY] "{name}" похож на "{similar}" — не добавляем новый.')
                    continue

                s = SubcategoryDropdown(subcategory_name=name)
                session.add(s)
                new_subcategories.append(s)
                existing_names.add(name)

            if new_subcategories:
                await session.commit()
                for s in new_subcategories:
                    await session.refresh(s)

            return existing_objs + new_subcategories

    async def add_customer(self, data: Sequence[VacancyIn]) -> list[CustomerDropdown]:
        async with AsyncSession(self.engine) as session:
            all_customer_names: set[str] = set()

            for vac in data:
                cus_name = self._extract_list(getattr(vac, "customer", None))
                for name in cus_name:
                    norm = self._normalize_name(name)
                    if norm:
                        all_customer_names.add(norm)

            if not all_customer_names:
                return []

            result = await session.execute(select(CustomerDropdown))
            existing_objs: List[CustomerDropdown] = list(result.scalars().all())
            existing_names: set[str] = {c.customer_name for c in existing_objs}

            new_customers: list[CustomerDropdown] = []

            for name in all_customer_names:
                if name in existing_names:
                    continue

                similar = self._find_similar(name, existing_names)
                if similar:
                    print(f'[CUSTOMER] "{name}" похож на "{similar}" — не добавляем новый.')
                    continue

                c = CustomerDropdown(customer_name=name)
                session.add(c)
                new_customers.append(c)
                existing_names.add(name)

            if new_customers:
                await session.commit()
                for c in new_customers:
                    await session.refresh(c)

            return existing_objs + new_customers

    async def add_manager(self, data: Sequence[VacancyIn]) -> list[ManagerDropdown]:
        async with AsyncSession(self.engine) as session:
            all_manager_name: set[str] = set()

            for vac in data:
                man_name = self._extract_list(getattr(vac, "manager_username", None))
                for name in man_name:
                    norm = self._normalize_name(name)
                    if norm:
                        all_manager_name.add(norm)

            if not all_manager_name:
                return []

            result = await session.execute(select(ManagerDropdown))
            existing_objs: List[ManagerDropdown] = list(result.scalars().all())
            existing_names: set[str] = {m.manager_name for m in existing_objs}

            new_managers: list[ManagerDropdown] = []

            for name in all_manager_name:
                if name in existing_names:
                    continue

                similar = self._find_similar(name, existing_names)
                if similar:
                    print(f'[MANAGER] "{name}" похож на "{similar}" — не добавляем новый.')
                    continue

                m = ManagerDropdown(manager_name=name)
                session.add(m)
                new_managers.append(m)
                existing_names.add(name)

            if new_managers:
                await session.commit()
                for m in new_managers:
                    await session.refresh(m)

            return existing_objs + new_managers

    async def add_location(self, data: Sequence[VacancyIn]) -> list[LocationDropdown]:
        async with AsyncSession(self.engine) as session:
            all_location_name: set[str] = set()

            for vac in data:
                loc_name = self._extract_list(getattr(vac, "location", None))
                for name in loc_name:
                    norm = self._normalize_name(name)
                    if norm:
                        all_location_name.add(norm)

            if not all_location_name:
                return []

            result = await session.execute(select(LocationDropdown))
            existing_objs: List[LocationDropdown] = list(result.scalars().all())
            existing_names: set[str] = {l.location_name for l in existing_objs}

            new_locations: list[LocationDropdown] = []

            for name in all_location_name:
                if name in existing_names:
                    continue

                similar = self._find_similar(name, existing_names)
                if similar:
                    print(f'[LOCATION] "{name}" похож на "{similar}" — не добавляем новый.')
                    continue

                l = LocationDropdown(location_name=name)
                session.add(l)
                new_locations.append(l)
                existing_names.add(name)

            if new_locations:
                await session.commit()
                for l in new_locations:
                    await session.refresh(l)

            return existing_objs + new_locations


    async def get_specializations(self) -> list[str]:
        async with AsyncSession(self.engine) as session:
            result = await session.execute(select(SpecializationDropdown.specialization_name))
            spec = result.scalars().all()
            print(spec)
            return spec

    async def get_candidate_specializations(self, user_id: int) -> list[str]:
        """
        Получить все уникальные специализации из кандидатов пользователя.
        Извлекает значения из поля specializations, парсит их и возвращает уникальный список.
        """
        from .database import CandidateProfileDB
        
        async with AsyncSession(self.engine) as session:
            result = await session.execute(
                select(CandidateProfileDB.specializations).where(
                    CandidateProfileDB.user_id == user_id,
                    CandidateProfileDB.specializations.isnot(None)
                )
            )
            all_specs = result.scalars().all()
            
            # Собираем все специализации в один set
            unique_specs = set()
            for spec_str in all_specs:
                if spec_str:
                    spec_list = self._extract_list(spec_str)
                    for spec in spec_list:
                        norm = self._normalize_name(spec)
                        if norm:
                            unique_specs.add(norm)
            
            return sorted(list(unique_specs))