import sys
import os
import asyncio
import logging
from sqlalchemy import select

# 1. Добавляем текущую директорию в пути поиска Python, 
# чтобы он видел папку 'app'
sys.path.append(os.getcwd())

# 2. Импорты из твоего проекта
# (Если Cursor подчеркнет их желтым — игнорируй, при запуске сработает)
from app.database.database import async_session_factory, User, UserRole
from app.core.security import get_password_hash

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Email системного пользователя для сбора резюме
SYSTEM_EMAIL = "cv@omega-solutions.ru"

async def create_system_user():
    print(f"🔄 Подключение к БД...")
    
    async with async_session_factory() as session:
        print(f"🔍 Поиск пользователя {SYSTEM_EMAIL}...")
        
        # 3. Ищем пользователя в базе
        query = select(User).where(User.email == SYSTEM_EMAIL)
        result = await session.execute(query)
        user = result.scalar_one_or_none()
        
        # 4. Если пользователь уже есть — ничего не делаем
        if user:
            print(f"✅ Пользователь уже существует!")
            print(f"   ID: {user.id}")
            print(f"   Email: {user.email}")
            return
        
        # 5. Если нет — создаем
        print(f"⚙️ Пользователь не найден. Создаю нового...")
        
        new_user = User(
            email=SYSTEM_EMAIL,
            # Генерируем хэш пароля (сам пароль нам знать не обязательно, под ним никто не будет логиниться руками)
            hashed_password=get_password_hash("system_omega_secret_2025_secure_pass"),
            role=UserRole.RECRUITER, # Даем роль рекрутера, чтобы он мог 'владеть' кандидатами
            is_active=True
        )
        
        session.add(new_user)
        await session.commit()
        await session.refresh(new_user)
        
        print(f"🚀 УСПЕХ! Системный пользователь создан.")
        print(f"   ID: {new_user.id}")
        print(f"   Email: {new_user.email}")

if __name__ == "__main__":
    # Запускаем асинхронную функцию
    try:
        asyncio.run(create_system_user())
    except Exception as e:
        print(f"❌ Произошла ошибка: {e}")
        