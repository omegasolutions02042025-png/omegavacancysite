import asyncio
import sys
import os
from sqlalchemy import select

# Настройка путей
sys.path.append(os.getcwd())

from app.database.database import async_session_factory, User, UserRole

async def unlock_first_admin():
    print(f"🔍 Ищу администратора в базе...")
    
    async with async_session_factory() as session:
        # Ищем ЛЮБОГО пользователя с ролью ADMIN
        query = select(User).where(User.role == UserRole.ADMIN)
        result = await session.execute(query)
        admin = result.first() # Берем первого попавшегося
        
        if not admin:
            print("❌ Админ не найден! В базе нет пользователей с ролью ADMIN.")
            return

        user = admin[0] # Извлекаем объект пользователя из кортежа
        print(f"✅ Нашел админа: {user.email}")
        
        # === ОТКЛЮЧАЕМ ВСЕ ПРОВЕРКИ ===
        
        # 1. Делаем активным (если ждал одобрения)
        user.is_active = True
        
        # 2. Убираем требование подтверждения почты (если есть такое поле)
        if hasattr(user, 'is_verified'):
            user.is_verified = True
        if hasattr(user, 'email_verified'):
            user.email_verified = True
            
        # 3. Отключаем 2FA / OTP (если есть такие поля)
        otp_fields = ["is_2fa_enabled", "two_factor_enabled", "otp_enabled", "mfa_enabled"]
        for field in otp_fields:
            if hasattr(user, field):
                setattr(user, field, False)
                print(f"   🔓 Отключено: {field}")

        session.add(user)
        await session.commit()
        
        print(f"🚀 УСПЕХ! Админ {user.email} разблокирован.")
        print("Попробуйте войти с вашим паролем. СМС/Код просить не должно.")

if __name__ == "__main__":
    asyncio.run(unlock_first_admin())