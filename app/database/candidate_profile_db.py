"""
Репозиторий для работы с CandidateProfile (система ролей).
Профиль кандидата связан с User через One-to-One отношение.
"""

from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.database import engine
from app.models.users import CandidateProfile, Grade


class CandidateProfileRepository:
    """
    Репозиторий для работы с профилями кандидатов (система ролей).
    """
    
    def __init__(self):
        """Инициализация репозитория с подключением к базе данных."""
        self.engine = engine

    async def get_by_user_id(self, user_id: int) -> Optional[CandidateProfile]:
        """
        Получить профиль кандидата по ID пользователя.
        
        Args:
            user_id: ID пользователя
            
        Returns:
            CandidateProfile: Профиль кандидата или None если не найден
        """
        async with AsyncSession(self.engine) as session:
            result = await session.execute(
                select(CandidateProfile).where(CandidateProfile.user_id == user_id)
            )
            return result.scalar_one_or_none()

    async def create_or_update(
        self,
        user_id: int,
        grade: Optional[Grade] = None,
        stack: Optional[list[str]] = None,
        bio: Optional[str] = None,
        experience_years: Optional[int] = None,
        resume_url: Optional[str] = None,
    ) -> CandidateProfile:
        """
        Создать или обновить профиль кандидата.
        
        Если профиль существует - обновляет только переданные поля.
        Если не существует - создает новый.
        
        Args:
            user_id: ID пользователя
            grade: Уровень кандидата
            stack: Технологический стек
            bio: Биография
            experience_years: Опыт работы в годах
            resume_url: URL резюме
            
        Returns:
            CandidateProfile: Созданный или обновленный профиль
        """
        async with AsyncSession(self.engine) as session:
            # Проверяем существующий профиль
            result = await session.execute(
                select(CandidateProfile).where(CandidateProfile.user_id == user_id)
            )
            profile = result.scalar_one_or_none()
            
            if profile:
                # Обновляем существующий профиль
                if grade is not None:
                    profile.grade = grade
                if stack is not None:
                    profile.stack = stack
                if bio is not None:
                    profile.bio = bio
                if experience_years is not None:
                    profile.experience_years = experience_years
                if resume_url is not None:
                    profile.resume_url = resume_url
            else:
                # Создаем новый профиль
                profile = CandidateProfile(
                    user_id=user_id,
                    grade=grade,
                    stack=stack,
                    bio=bio,
                    experience_years=experience_years,
                    resume_url=resume_url,
                )
                session.add(profile)
            
            await session.commit()
            await session.refresh(profile)
            return profile

    async def update_resume_url(self, user_id: int, resume_url: str) -> Optional[CandidateProfile]:
        """
        Обновить URL резюме в профиле кандидата.
        
        Args:
            user_id: ID пользователя
            resume_url: URL резюме
            
        Returns:
            CandidateProfile: Обновленный профиль или None если не найден
        """
        async with AsyncSession(self.engine) as session:
            result = await session.execute(
                select(CandidateProfile).where(CandidateProfile.user_id == user_id)
            )
            profile = result.scalar_one_or_none()
            
            if not profile:
                return None
            
            profile.resume_url = resume_url
            await session.commit()
            await session.refresh(profile)
            return profile

