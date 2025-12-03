from typing import Optional, Dict, Any
from sqlmodel import select, func, or_
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database.database import CandidateProfileDB
from app.models.candidate import GPTCandidateProfile
from app.database.database import engine, Vacancy

import re
import logging

# БЫЛО:
# from rapidfuzz import fuzz

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)


class CandidateRepository:
    def __init__(self):
        self.engine = engine

    @staticmethod
    def norm(val: Optional[str]) -> str:
        return (val or "").strip().lower().replace("-", "_").replace(" ", "_")

    @staticmethod
    def split_list(s: Optional[str]) -> set[str]:
        if not s:
            return set()
        return {
            item.strip().lower()
            for item in s.split(",")
            if item.strip()
        }

    @staticmethod
    def csv_to_list(value: Optional[str]) -> list[str]:
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
    def coverage_percent(vacancy_items: set[str], candidate_items: set[str]) -> float:
        """
        Покрытие в процентах: для КАЖДОГО термина из вакансии
        считаем его покрытым, если он входит как подстрока
        в ЛЮБОЙ термин кандидата или наоборот.

        Примеры:
        - 'devops'  vs 'devops engineer'        → матч
        - 'gitlab ci' vs 'gitlab ci/cd'         → матч
        - 'python'  vs 'python developer'       → матч
        - 'java'    vs 'javascript developer'   → матч (осознанно, но это уже вопрос к словарю)
        """
        if not vacancy_items:
            return 0.0

        matched = 0

        for v in vacancy_items:
            v_norm = v.strip().lower()
            for c in candidate_items:
                c_norm = c.strip().lower()
                if v_norm in c_norm or c_norm in v_norm:
                    matched += 1
                    break

        return (matched / len(vacancy_items)) * 100.0

    @staticmethod
    def english_rank(level: Optional[str]) -> int:
        """
        Ранг уровня английского.
        Чем БОЛЬШЕ число — тем ВЫШЕ уровень.

        Самый высокий: C2, потом C1, B2, B1, A2, A1.
        Всё неизвестное/пустое считаем 0.
        """
        if not level:
            return 0
        lvl = level.strip().lower()

        mapping = {
            "a1": 1,
            "a2": 2,
            "b1": 3,
            "b2": 4,
            "c1": 5,
            "c2": 6,
        }
        return mapping.get(lvl, 0)

    @staticmethod
    def tfidf_similarity(text1: Optional[str], text2: Optional[str]) -> float:
        """
        Схожесть двух строк по TF-IDF + cosine similarity.
        Возвращает значение 0–100 (проценты).
        """
        if not text1 or not text2:
            return 0.0

        t1 = text1.strip().lower()
        t2 = text2.strip().lower()
        if not t1 or not t2:
            return 0.0

        try:
            vectorizer = TfidfVectorizer()
            X = vectorizer.fit_transform([t1, t2])
            sim = cosine_similarity(X[0:1], X[1:2])[0, 0]
            if sim is None:
                return 0.0
            return float(sim * 100.0)
        except Exception as e:
            logger.warning(f"tfidf_similarity error: {e}")
            return 0.0

    async def candidate_profile_to_db(
        self,
        profile: GPTCandidateProfile,
        user_id: int,
    ) -> CandidateProfileDB:
        async with AsyncSession(self.engine) as session:
            # считаем следующий номер кандидата для пользователя
            result = await session.exec(
                select(func.max(CandidateProfileDB.number_for_user)).where(
                    CandidateProfileDB.user_id == user_id
                )
            )
            last_num: Optional[int] = result.one_or_none()
            next_number = (last_num or 0) + 1

            db_obj = CandidateProfileDB(
                user_id=user_id,
                number_for_user=next_number,

                # personal
                first_name=profile.personal.first_name,
                last_name=profile.personal.last_name,
                middle_name=profile.personal.middle_name,
                title=profile.personal.title,
                email=profile.personal.email,
                telegram=profile.personal.telegram,
                phone=profile.personal.phone,
                linkedin=profile.personal.linkedin,
                github=profile.personal.github,
                portfolio=profile.personal.portfolio,
                about=profile.personal.about,

                # main
                salary_usd=profile.main.salary_usd,
                currencies=profile.main.currencies,
                grade=profile.main.grade,
                work_format=profile.main.work_format,
                employment_type=profile.main.employment_type,
                company_types=profile.main.company_types,
                specializations=profile.main.specializations,
                skills=profile.main.skills,

                # location
                city=profile.location.city,
                timezone=profile.location.timezone,
                regions=profile.location.regions,
                countries=profile.location.countries,
                relocation=profile.location.relocation,

                # JSON-поля
                experience=[e.model_dump(exclude_none=True) for e in profile.experience] or None,
                education=[e.model_dump(exclude_none=True) for e in profile.education] or None,
                courses=[c.model_dump(exclude_none=True) for c in profile.courses] or None,
                projects=[p.model_dump(exclude_none=True) for p in profile.projects] or None,

                english_level=profile.english_level,
            )

            session.add(db_obj)
            await session.commit()
            await session.refresh(db_obj)
            return db_obj

    async def get_candidate_profile_for_candidate_id_and_user_id(
        self,
        candidate_id: int,
        user_id: int
    ) -> CandidateProfileDB:
        async with AsyncSession(self.engine) as session:
            result = await session.exec(
                select(CandidateProfileDB).where(
                    CandidateProfileDB.number_for_user == candidate_id,
                    CandidateProfileDB.user_id == user_id
                )
            )
            return result.one_or_none()

    async def get_candidate_id_by_fullname(
        self,
        user_id: int,
        candidate_fullname: str
    ) -> Optional[int]:
        """
        Получить number_for_user кандидата по его полному имени.
        
        Args:
            user_id: ID пользователя
            candidate_fullname: Полное имя кандидата (например, "Иванов Иван Иванович")
            
        Returns:
            int: number_for_user кандидата или None если не найден
        """
        async with AsyncSession(self.engine) as session:
            # Получаем всех кандидатов пользователя
            result = await session.exec(
                select(CandidateProfileDB).where(
                    CandidateProfileDB.user_id == user_id
                )
            )
            candidates = result.all()
            
            # Нормализуем искомое имя (убираем лишние пробелы, приводим к нижнему регистру)
            search_name = " ".join(candidate_fullname.split()).lower()
            
            # Ищем кандидата, сравнивая полное имя
            for candidate in candidates:
                # Формируем полное имя из отдельных полей
                name_parts = []
                if candidate.first_name:
                    name_parts.append(candidate.first_name)
                if candidate.last_name:
                    name_parts.append(candidate.last_name)
                if candidate.middle_name:
                    name_parts.append(candidate.middle_name)
                
                full_name = " ".join(name_parts)
                if not full_name:
                    continue
                
                # Нормализуем имя кандидата
                candidate_name = " ".join(full_name.split()).lower()
                
                # Сравниваем имена (точное совпадение или частичное)
                if candidate_name == search_name or search_name in candidate_name or candidate_name in search_name:
                    return candidate.number_for_user
            
            return None

    async def update_candidate_for_user(
        self,
        candidate_id: int,
        user_id: int,
        payload: dict[str, Any],
    ) -> CandidateProfileDB:
        """
        Обновить кандидата полями из payload, если он принадлежит пользователю.
        Бросает ValueError, если кандидат не найден или чужой.
        """
        async with AsyncSession(self.engine) as session:
            print(candidate_id)
            res = await session.exec(
                select(CandidateProfileDB).where(
                    CandidateProfileDB.number_for_user == candidate_id,
                    CandidateProfileDB.user_id == user_id
                )
            )
            candidate = res.one_or_none()
            if not candidate:
                return

            # простые поля
            simple_fields = [
                "first_name",
                "last_name",
                "middle_name",  
                "title",
                "email",
                "telegram",
                "phone",
                "linkedin",
                "github",
                "portfolio",
                "about",
                "salary_usd",
                "currencies",
                "grade",
                "work_format",
                "employment_type",
                "company_types",
                "specializations",
                "skills",
                "city",
                "timezone",
                "regions",
                "countries",
                "relocation",
                "english_level",
            ]
            for field in simple_fields:
                if field in payload:
                    value = payload[field]
                    # Сохраняем значение (может быть None, пустая строка или текст)
                    # Для строковых полей пустая строка сохраняется как пустая строка
                    if value == "" and field in ["regions", "city", "timezone", "countries", "relocation"]:
                        setattr(candidate, field, "")
                    else:
                        setattr(candidate, field, value)

            # JSON-поля
            if "experience" in payload and isinstance(payload["experience"], list):
                candidate.experience = payload["experience"]
            if "education" in payload and isinstance(payload["education"], list):
                candidate.education = payload["education"]
            if "courses" in payload and isinstance(payload["courses"], list):
                candidate.courses = payload["courses"]
            if "projects" in payload and isinstance(payload["projects"], list):
                candidate.projects = payload["projects"]

            session.add(candidate)
            await session.commit()
            await session.refresh(candidate)
            return candidate

    async def get_all_candidates_for_user(
        self,
        user_id: int,
        search_query: Optional[str] = None,
        specialization_filter: Optional[str] = None,
    ):
        """
        Получить всех кандидатов пользователя с опциональной фильтрацией.
        
        Args:
            user_id: ID пользователя
            search_query: Поиск по имени (first_name, last_name, middle_name) и title
            specialization_filter: Фильтр по специализации (точное совпадение или вхождение)
        """
        from sqlalchemy import or_
        
        async with AsyncSession(self.engine) as session:
            query = select(CandidateProfileDB).where(
                CandidateProfileDB.user_id == user_id
            )
            
            # Поиск по имени и title
            if search_query:
                search_lower = search_query.lower().strip()
                query = query.where(
                    or_(
                        func.lower(CandidateProfileDB.first_name).ilike(f"%{search_lower}%"),
                        func.lower(CandidateProfileDB.last_name).ilike(f"%{search_lower}%"),
                        func.lower(CandidateProfileDB.middle_name).ilike(f"%{search_lower}%"),
                        func.lower(CandidateProfileDB.title).ilike(f"%{search_lower}%"),
                    )
                )
            
            # Фильтр по специализации
            if specialization_filter:
                # Ищем специализацию в строке specializations (может быть через запятую, точку с запятой и т.д.)
                query = query.where(
                    func.lower(CandidateProfileDB.specializations).ilike(
                        f"%{specialization_filter.lower()}%"
                    )
                )
            
            result = await session.exec(
                query.order_by(CandidateProfileDB.number_for_user.desc())
            )
            return result.all()

    async def delete_candidate_for_user(self, candidate_id: int, user_id: int) -> None:
        async with AsyncSession(self.engine) as session:
            result = await session.exec(
                select(CandidateProfileDB).where(
                    CandidateProfileDB.number_for_user == candidate_id,
                    CandidateProfileDB.user_id == user_id
                )
            )
            candidate = result.one_or_none()
            if candidate:
                await session.delete(candidate)
                await session.commit()
                return True
            else:
                return

    async def get_matching_candidates_for_vacancy(
        self,
        vacancy_id: str,
        owner_user_id: int | None = None,
        skills_threshold: float = 80.0,
        specs_threshold: float = 80.0,
    ) -> list[dict]:
        """
        Подбор кандидатов под вакансию:

        — 100% совпадение по:
            work_format, employment_type, grade
        — английский: кандидат ДОЛЖЕН БЫТЬ ВЫШЕ либо НА УРОВНЕ
          по нашей шкале, где A1 > A2 > B1 > B2 > C1 > C2
        — локация: город кандидата должен содержать одну
          из стран/регионов из vacancy.location
        — ≥ skills_threshold % совпадения по skills
        — ≥ specs_threshold % совпадения по specializations
        """

        async with AsyncSession(self.engine) as session:
            # 1) грузим вакансию по vacancy_id
            vacancy_stmt = select(Vacancy).where(Vacancy.vacancy_id == str(vacancy_id))
            vacancy_res = await session.exec(vacancy_stmt)
            vacancy = vacancy_res.one_or_none()

            print(f"=== MATCHING for vacancy_id={vacancy_id} ===")
            print("Raw vacancy from DB:", vacancy)

            if not vacancy:
                print(f"Vacancy {vacancy_id} not found")
                return []

            # нормализация полей вакансии
            v_location_raw = (vacancy.location or "").strip()
            allowed_locations = [
                part.strip().lower()
                for part in re.split(r"[;,/]", v_location_raw)
                if part.strip()
            ]

            v_work_format = self.norm(vacancy.work_format)
            v_employment_type = self.norm(vacancy.employment_type)
            v_grade = self.norm(vacancy.grade)
            # сырой уровень английского вакансии
            v_english_raw = vacancy.english_level
            v_english_norm = self.norm(vacancy.english_level)
            v_eng_rank = self.english_rank(v_english_raw)

            v_skills = self.split_list(vacancy.skills)
            v_specs = self.split_list(vacancy.specializations)

            print(
                "Vacancy normed:",
                f"location_raw={v_location_raw!r}, allowed_locations={allowed_locations}",
                f"work_format={v_work_format!r}, employment_type={v_employment_type!r},",
                f"grade={v_grade!r}, english_raw={v_english_raw!r}, english_rank={v_eng_rank}",
            )
            print("Vacancy skills:", v_skills)
            print("Vacancy specs:", v_specs)

            # 2) вытаскиваем всех кандидатов пользователя (или всех, если owner_user_id=None)
            stmt = select(CandidateProfileDB)
            if owner_user_id:
                stmt = stmt.where(CandidateProfileDB.user_id == owner_user_id)

            res = await session.exec(stmt)
            candidates: list[CandidateProfileDB] = list(res.all())
            print(f"Total candidates loaded for user {owner_user_id}: {len(candidates)}")

            result: list[dict] = []

            # 3) фильтр по хард-полям + скиллам/спецам
            for c in candidates:
                # Формируем полное имя из отдельных полей
                full_name_parts = []
                if c.first_name:
                    full_name_parts.append(c.first_name)
                if c.last_name:
                    full_name_parts.append(c.last_name)
                if c.middle_name:
                    full_name_parts.append(c.middle_name)
                full_name = " ".join(full_name_parts) if full_name_parts else "Без имени"

                # хард-поля
                c_work_format = self.norm(c.work_format)
                c_employment_type = self.norm(c.employment_type)
                c_grade = self.norm(c.grade)
                c_english_raw = c.english_level
                c_english_norm = self.norm(c.english_level)
                c_eng_rank = self.english_rank(c_english_raw)

                print(
                    "Hard fields:",
                    f"work_format={c_work_format!r}, employment_type={c_employment_type!r},",
                    f"grade={c_grade!r}, english_raw={c_english_raw!r} (rank={c_eng_rank}),",
                    f"city={c.city!r}",
                )

                # work_format / employment_type / grade — строгое равенство
                if v_work_format and c_work_format != v_work_format:
                    print(
                        f"Skip candidate {c.id}: work_format mismatch "
                        f"{c_work_format!r} != {v_work_format!r}"
                    )
                    continue
                if v_employment_type and c_employment_type != v_employment_type:
                    print(
                        f"Skip candidate {c.id}: employment_type mismatch "
                        f"{c_employment_type!r} != {v_employment_type!r}"
                    )
                    continue
                if v_grade and c_grade != v_grade:
                    print(
                        f"Skip candidate {c.id}: grade mismatch "
                        f"{c_grade!r} != {v_grade!r}"
                    )
                    continue

                # АНГЛИЙСКИЙ: кандидат должен быть НЕ НИЖЕ требования
                if v_english_norm:
                    print(
                        f"[ENGLISH] vacancy={v_english_raw!r} (rank={v_eng_rank}) | "
                        f"candidate={c_english_raw!r} (rank={c_eng_rank})"
                    )
                    if c_eng_rank < v_eng_rank:
                        print(
                            f"Skip candidate {c.id}: english too low "
                            f"(candidate_rank={c_eng_rank} < vacancy_rank={v_eng_rank})"
                        )
                        continue

                # ЛОКАЦИЯ
                if allowed_locations:
                    city_norm = (c.countries or "").lower()
                    ok_location = any(loc in city_norm for loc in allowed_locations)
                    print(
                        "Location check:",
                        f"city_norm={city_norm!r}, allowed_locations={allowed_locations}, ok={ok_location}",
                    )
                    if not ok_location:
                        print(f"Skip candidate {c.id}: location not allowed")
                        continue

                # СКИЛЛЫ / СПЕЦЫ
                c_skills_set = self.split_list(c.skills)
                c_specs_set = self.split_list(c.specializations)

                skills_cov = self.coverage_percent(v_skills, c_skills_set)
                specs_cov = self.coverage_percent(v_specs, c_specs_set)

                # === ЗАМЕНА rapidfuzz НА TF-IDF ===
                skills_ratio = 0.0
                specs_ratio = 0.0
                if vacancy.skills and c.skills:
                    skills_ratio = self.tfidf_similarity(
                        (vacancy.skills or ""),
                        (c.skills or ""),
                    )
                if vacancy.specializations and c.specializations:
                    specs_ratio = self.tfidf_similarity(
                        (vacancy.specializations or ""),
                        (c.specializations or ""),
                    )

                print(
                    "Skills check:",
                    f"v_skills={v_skills}, c_skills={c_skills_set},",
                    f"coverage={skills_cov:.1f}%, ratio={skills_ratio:.1f}",
                )
                print(
                    "Specs  check:",
                    f"v_specs={v_specs}, c_specs={c_specs_set},",
                    f"coverage={specs_cov:.1f}%, ratio={specs_ratio:.1f}",
                )

                if (
                    skills_cov >= skills_threshold
                    and specs_cov >= specs_threshold
                    and skills_ratio >= skills_threshold
                    and specs_ratio >= specs_threshold
                ):
                    print(
                        f"Candidate {c.id} PASSED: "
                        f"skills_cov={skills_cov:.1f}, specs_cov={specs_cov:.1f}, "
                        f"skills_ratio={skills_ratio:.1f}, specs_ratio={specs_ratio:.1f}"
                    )
                    result.append(
                        {
                            # базовые идентификаторы
                            "id": c.id,
                            "user_id": c.user_id,
                            "number_for_user": c.number_for_user,

                            # ФИО и позиция
                            "full_name": full_name,
                            "title": c.title,

                            # контакты
                            "email": c.email,
                            "telegram": c.telegram,
                            "phone": c.phone,
                            "linkedin": c.linkedin,
                            "github": c.github,
                            "portfolio": c.portfolio,

                            # о себе
                            "about": c.about,

                            # деньги
                            "salary_usd": c.salary_usd,
                            "currencies": c.currencies,

                            # грейды / форматы
                            "grade": c.grade,
                            "work_format": c.work_format,
                            "employment_type": c.employment_type,
                            "company_types": c.company_types,

                            # навыки и специализации
                            "specializations": c.specializations,
                            "skills": c.skills,

                            # локация
                            "city": c.city,
                            "location": c.countries,        # для фронта, который ждёт location
                            "timezone": c.timezone,
                            "regions": c.regions,
                            "relocation": c.relocation,

                            # опыт / образование
                            "experience": c.experience,
                            "education": c.education,
                            "courses": c.courses,
                            "projects": c.projects,

                            # английский
                            "english_level": c.english_level,

                            # метрики совпадения
                            "skills_coverage": round(skills_cov, 1),
                            "specs_coverage": round(specs_cov, 1),
                            "skills_ratio": round(skills_ratio, 1),
                            "specs_ratio": round(specs_ratio, 1),
                        }
                    )
                else:
                    print(
                        f"Candidate {c.id} FAILED thresholds: "
                        f"skills_cov={skills_cov:.1f} (need>={skills_threshold:.1f}), "
                        f"specs_cov={specs_cov:.1f} (need>={specs_threshold:.1f}), "
                        f"skills_ratio={skills_ratio:.1f} (need>={skills_threshold:.1f}), "
                        f"specs_ratio={specs_ratio:.1f} (need>={specs_threshold:.1f})"
                    )

            print(f"\nTotal matched candidates for vacancy {vacancy_id}: {len(result)}")
            return result

    async def get_candidate_by_id_and_user_id(
        self,
        number_for_user: int,
        user_id: int
    ) -> CandidateProfileDB | None:
        async with AsyncSession(self.engine) as session:
            stmt = select(CandidateProfileDB).where(
                CandidateProfileDB.number_for_user == number_for_user,
                CandidateProfileDB.user_id == user_id
            )
            res = await session.exec(stmt)
            return res.one_or_none()

    async def merge_candidate_profile(
        self,
        existing_candidate: CandidateProfileDB,
        new_profile: GPTCandidateProfile,
    ) -> CandidateProfileDB:
        """
        Объединяет существующий профиль кандидата с новым профилем из обновленного резюме.
        
        Правила слияния:
        - Для полей где значение None - заполняем из нового резюме
        - Для строковых полей - если старое None или пустое, берем новое, иначе оставляем старое
        - Для массивов (experience, education, courses, projects) - дополняем новыми данными
        """
        async with AsyncSession(self.engine) as session:
            # Загружаем кандидата в сессию для отслеживания изменений
            result = await session.exec(
                select(CandidateProfileDB).where(
                    CandidateProfileDB.id == existing_candidate.id
                )
            )
            candidate = result.one_or_none()
            if not candidate:
                raise ValueError("Кандидат не найден в БД")

            # ===== PERSONAL =====
            # Приоритет: если старое None или пустое - берем новое
            if not candidate.first_name:
                candidate.first_name = new_profile.personal.first_name
            if not candidate.last_name:
                candidate.last_name = new_profile.personal.last_name
            if not candidate.middle_name:
                candidate.middle_name = new_profile.personal.middle_name
            if not candidate.title:
                candidate.title = new_profile.personal.title
            if not candidate.email:
                candidate.email = new_profile.personal.email
            if not candidate.telegram:
                candidate.telegram = new_profile.personal.telegram
            if not candidate.phone:
                candidate.phone = new_profile.personal.phone
            if not candidate.linkedin:
                candidate.linkedin = new_profile.personal.linkedin
            if not candidate.github:
                candidate.github = new_profile.personal.github
            if not candidate.portfolio:
                candidate.portfolio = new_profile.personal.portfolio
            if not candidate.about:
                candidate.about = new_profile.personal.about

            # ===== MAIN =====
            if candidate.salary_usd is None:
                candidate.salary_usd = new_profile.main.salary_usd
            if not candidate.currencies:
                candidate.currencies = new_profile.main.currencies
            if not candidate.grade:
                candidate.grade = new_profile.main.grade
            if not candidate.work_format:
                candidate.work_format = new_profile.main.work_format
            if not candidate.employment_type:
                candidate.employment_type = new_profile.main.employment_type
            if not candidate.company_types:
                candidate.company_types = new_profile.main.company_types
            if not candidate.specializations:
                candidate.specializations = new_profile.main.specializations
            if not candidate.skills:
                candidate.skills = new_profile.main.skills

            # ===== LOCATION =====
            if not candidate.city:
                candidate.city = new_profile.location.city
            if not candidate.timezone:
                candidate.timezone = new_profile.location.timezone
            if not candidate.regions:
                candidate.regions = new_profile.location.regions
            if not candidate.countries:
                candidate.countries = new_profile.location.countries
            if not candidate.relocation:
                candidate.relocation = new_profile.location.relocation

            # ===== ENGLISH LEVEL =====
            if not candidate.english_level:
                candidate.english_level = new_profile.english_level

            # ===== МАССИВЫ: ОБЪЕДИНЯЕМ ДАННЫЕ =====
            # Опыт работы
            existing_exp = candidate.experience or []
            new_exp = [e.model_dump(exclude_none=True) for e in new_profile.experience] if new_profile.experience else []
            # Объединяем, избегая дубликатов по ключевым полям
            merged_exp = list(existing_exp)
            for new_item in new_exp:
                # Проверяем, нет ли уже такого опыта (по компании и должности)
                is_duplicate = False
                for existing_item in existing_exp:
                    if (existing_item.get("company") == new_item.get("company") and
                        existing_item.get("title") == new_item.get("title")):
                        is_duplicate = True
                        break
                if not is_duplicate and any(new_item.values()):
                    merged_exp.append(new_item)
            candidate.experience = merged_exp if merged_exp else None

            # Образование
            existing_edu = candidate.education or []
            new_edu = [e.model_dump(exclude_none=True) for e in new_profile.education] if new_profile.education else []
            merged_edu = list(existing_edu)
            for new_item in new_edu:
                # Проверяем дубликаты по университету и степени
                is_duplicate = False
                for existing_item in existing_edu:
                    if (existing_item.get("university") == new_item.get("university") and
                        existing_item.get("degree") == new_item.get("degree")):
                        is_duplicate = True
                        break
                if not is_duplicate and any(new_item.values()):
                    merged_edu.append(new_item)
            candidate.education = merged_edu if merged_edu else None

            # Курсы
            existing_courses = candidate.courses or []
            new_courses = [c.model_dump(exclude_none=True) for c in new_profile.courses] if new_profile.courses else []
            merged_courses = list(existing_courses)
            for new_item in new_courses:
                # Проверяем дубликаты по названию и организации
                is_duplicate = False
                for existing_item in existing_courses:
                    if (existing_item.get("name") == new_item.get("name") and
                        existing_item.get("organization") == new_item.get("organization")):
                        is_duplicate = True
                        break
                if not is_duplicate and any(new_item.values()):
                    merged_courses.append(new_item)
            candidate.courses = merged_courses if merged_courses else None

            # Проекты
            existing_projects = candidate.projects or []
            new_projects = [p.model_dump(exclude_none=True) for p in new_profile.projects] if new_profile.projects else []
            merged_projects = list(existing_projects)
            for new_item in new_projects:
                # Проверяем дубликаты по названию проекта
                is_duplicate = False
                for existing_item in existing_projects:
                    if existing_item.get("name") == new_item.get("name"):
                        is_duplicate = True
                        break
                if not is_duplicate and any(new_item.values()):
                    merged_projects.append(new_item)
            candidate.projects = merged_projects if merged_projects else None

            session.add(candidate)
            await session.commit()
            await session.refresh(candidate)
            return candidate