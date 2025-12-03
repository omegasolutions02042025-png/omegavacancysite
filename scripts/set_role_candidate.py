import asyncio
import sys
import os
from sqlalchemy import select, update

# Добавляем пути
sys.path.append(os.getcwd())

from app.database.database import async_session_factory, User, UserRole

# Email пользователя, которого вы только что создали
TARGET_EMAIL = "test@candidate.com" 

async def make_user_candidate():
    async with async_session_factory() as session:
        print(f"🔍 Ищу пользователя {TARGET_EMAIL}...")
        
        # Находим пользователя
        query = select(User).where(User.email == TARGET_EMAIL)
        result = await session.execute(query)
        user = result.scalar_one_or_none()
        
        if not user:
            print(f"❌ Пользователь не найден! Сначала зарегистрируйтесь на сайте.")
            return

        print(f"👤 Текущая роль: {user.role}")
        
        # Меняем роль на CANDIDATE
        user.role = UserRole.CANDIDATE
        session.add(user)
        await session.commit()
        
        print(f"✅ УСПЕХ! Роль пользователя {TARGET_EMAIL} изменена на CANDIDATE.")
        print("Теперь можно заходить в дашборд.")

if __name__ == "__main__":
    asyncio.run(make_user_candidate())