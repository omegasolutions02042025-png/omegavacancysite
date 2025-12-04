from typing import Optional, List
from datetime import datetime
import secrets
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .database import RegistrationRequest, User, engine


class RegistrationRepository:
    """
    Репозиторий для работы с заявками на регистрацию пользователей.
    
    Управляет созданием заявок, подтверждением email и одобрением/отклонением администратором.
    """
    
    def __init__(self):
        """Инициализация репозитория с подключением к базе данных."""
        self.engine = engine

    async def create_request(
        self, 
        email: str, 
        password: str,
        first_name: str = None,
        last_name: str = None,
        middle_name: str = None,
        phone: str = None,
        role = None,
        specialization: str = None,
        experience: str = None,
        resume: str = None,
        pd_consent: bool = False,
        pd_consent_at: str = None,
        pd_consent_email: str = None,
        pd_consent_ip: str = None,
    ) -> Optional[RegistrationRequest]:
        """
        Создать новую заявку на регистрацию.
        
        Проверяет что пользователь не существует и нет активной заявки.
        Генерирует токен для верификации email.
        """
        async with AsyncSession(self.engine) as session:
            # Проверяем что пользователь не существует
            existing_user = await session.execute(
                select(User).where(User.email == email)
            )
            if existing_user.scalars().first():
                return None
            
            # Проверяем что нет активной заявки
            existing_request = await session.execute(
                select(RegistrationRequest).where(RegistrationRequest.email == email)
            )
            if existing_request.scalars().first():
                return None
            
            # Генерируем токен для верификации email
            verification_token = secrets.token_urlsafe(32)
            
            request = RegistrationRequest(
                email=email,
                password=password,  # Храним в открытом виде
                first_name=first_name,
                last_name=last_name,
                middle_name=middle_name,
                phone=phone,
                role=role,
                specialization=specialization,
                experience=experience,
                resume=resume,
                verification_token=verification_token,
                is_email_verified=False,
                is_approved=None,
                created_at=datetime.now().isoformat(),
                pd_consent=pd_consent,
                pd_consent_at=pd_consent_at,
                pd_consent_email=pd_consent_email,
                pd_consent_ip=pd_consent_ip,
            )
            session.add(request)
            await session.commit()
            await session.refresh(request)
            print(f"[REGISTRATION_DB] ✅ Создана заявка на регистрацию: {email}")
            return request

    async def verify_email(self, token: str) -> Optional[RegistrationRequest]:
        """
        Подтвердить email пользователя по токену из письма.
        
        Args:
            token: Токен верификации из письма
            
        Returns:
            RegistrationRequest: Заявка с подтвержденным email или None если токен неверный
        """
        async with AsyncSession(self.engine) as session:
            result = await session.execute(
                select(RegistrationRequest).where(
                    RegistrationRequest.verification_token == token,
                    RegistrationRequest.is_email_verified == False
                )
            )
            request = result.scalars().first()
            
            if not request:
                return None
            
            request.is_email_verified = True
            request.verified_at = datetime.now().isoformat()
            await session.commit()
            await session.refresh(request)
            print(f"[REGISTRATION_DB] ✅ Email подтвержден: {request.email}")
            return request

    async def get_pending_requests(self) -> List[RegistrationRequest]:
        """
        Получить все заявки ожидающие одобрения администратора.
        
        Возвращает только заявки с подтвержденным email, которые еще не обработаны.
        
        Returns:
            List[RegistrationRequest]: Список заявок ожидающих рассмотрения
        """
        async with AsyncSession(self.engine) as session:
            result = await session.execute(
                select(RegistrationRequest).where(
                    RegistrationRequest.is_email_verified == True,
                    RegistrationRequest.is_approved == None
                )
            )
            return list(result.scalars().all())

    async def get_by_id(self, request_id: int) -> Optional[RegistrationRequest]:
        """
        Получить заявку по ID.
        
        Args:
            request_id: ID заявки
            
        Returns:
            RegistrationRequest: Заявка или None если не найдена
        """
        async with AsyncSession(self.engine) as session:
            result = await session.execute(
                select(RegistrationRequest).where(RegistrationRequest.id == request_id)
            )
            return result.scalars().first()

    async def approve_request(self, request_id: int, admin_id: int) -> Optional[User]:
        """
        Одобрить заявку на регистрацию и создать пользователя в системе.
        
        Создает пользователя с данными из заявки и отмечает заявку как одобренную.
        
        Args:
            request_id: ID заявки
            admin_id: ID администратора, который одобрил заявку
            
        Returns:
            User: Созданный пользователь или None если заявка не найдена/уже обработана
        """
        async with AsyncSession(self.engine) as session:
            result = await session.execute(
                select(RegistrationRequest).where(RegistrationRequest.id == request_id)
            )
            request = result.scalars().first()
            
            if not request or not request.is_email_verified or request.is_approved is not None:
                return None
            
            # Создаем пользователя со всеми полями профиля
            user = User(
                email=request.email,
                password=request.password,  # Храним в открытом виде
                first_name=request.first_name,
                last_name=request.last_name,
                middle_name=request.middle_name,
                phone=request.phone,
                role=request.role if request.role else None,
                specialization=request.specialization,
                experience=request.experience,
                resume=request.resume,
                created_by_admin=admin_id,
                created_at=datetime.now().isoformat(),
                work_telegram="",
                work_email="",
                work_telegram_session_name="",
                work_email_app_pass="",
                pd_consent=request.pd_consent,
                pd_consent_at=request.pd_consent_at,
                pd_consent_email=request.pd_consent_email,
                pd_consent_ip=request.pd_consent_ip,
            )
            session.add(user)
            
            # Обновляем заявку
            request.is_approved = True
            request.approved_by_admin = admin_id
            request.processed_at = datetime.now().isoformat()
            
            await session.commit()
            await session.refresh(user)
            print(f"[REGISTRATION_DB] ✅ Заявка одобрена, создан пользователь: {user.email}")
            return user

    async def reject_request(self, request_id: int, admin_id: int) -> bool:
        """
        Отклонить заявку на регистрацию.
        
        Отмечает заявку как отклоненную без создания пользователя.
        
        Args:
            request_id: ID заявки
            admin_id: ID администратора, который отклонил заявку
            
        Returns:
            bool: True если заявка успешно отклонена, False если не найдена/уже обработана
        """
        async with AsyncSession(self.engine) as session:
            result = await session.execute(
                select(RegistrationRequest).where(RegistrationRequest.id == request_id)
            )
            request = result.scalars().first()
            
            if not request or not request.is_email_verified or request.is_approved is not None:
                return False
            
            request.is_approved = False
            request.approved_by_admin = admin_id
            request.processed_at = datetime.now().isoformat()
            
            await session.commit()
            print(f"[REGISTRATION_DB] ❌ Заявка отклонена: {request.email}")
            return True


# Singleton
registration_repository = RegistrationRepository()
