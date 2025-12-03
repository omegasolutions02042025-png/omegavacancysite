"""
Миграция: Добавление полей администратора
Запуск: python scripts/migrate_add_admin.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.database import engine


async def run_migration():
    """Применить миграцию для добавления полей администратора"""
    
    print("=" * 60)
    print("🔄 МИГРАЦИЯ: Добавление полей администратора")
    print("=" * 60)
    
    async with AsyncSession(engine) as session:
        try:
            # 1. Создать таблицу admins
            print("\n1️⃣ Создание таблицы admins...")
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS admins (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR NOT NULL UNIQUE,
                    hashed_password VARCHAR NOT NULL,
                    created_at VARCHAR
                )
            """))
            print("   ✅ Таблица admins создана")
            
            # 2. Проверить существование колонок
            print("\n2️⃣ Проверка существующих колонок в users...")
            result = await session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users'
            """))
            existing_columns = [row[0] for row in result.fetchall()]
            print(f"   Существующие колонки: {', '.join(existing_columns)}")
            
            # 3. Добавить created_by_admin если её нет
            if 'created_by_admin' not in existing_columns:
                print("\n3️⃣ Добавление колонки created_by_admin...")
                await session.execute(text("""
                    ALTER TABLE users 
                    ADD COLUMN created_by_admin INTEGER
                """))
                print("   ✅ Колонка created_by_admin добавлена")
            else:
                print("\n3️⃣ Колонка created_by_admin уже существует")
            
            # 4. Добавить created_at если её нет
            if 'created_at' not in existing_columns:
                print("\n4️⃣ Добавление колонки created_at...")
                await session.execute(text("""
                    ALTER TABLE users 
                    ADD COLUMN created_at VARCHAR
                """))
                print("   ✅ Колонка created_at добавлена")
            else:
                print("\n4️⃣ Колонка created_at уже существует")
            
            # 5. Добавить внешний ключ если его нет
            print("\n5️⃣ Проверка внешнего ключа...")
            try:
                await session.execute(text("""
                    ALTER TABLE users 
                    ADD CONSTRAINT fk_users_created_by_admin 
                    FOREIGN KEY (created_by_admin) REFERENCES admins(id) 
                    ON DELETE SET NULL
                """))
                print("   ✅ Внешний ключ добавлен")
            except Exception as e:
                if "already exists" in str(e).lower():
                    print("   ℹ️ Внешний ключ уже существует")
                else:
                    print(f"   ⚠️ Не удалось добавить внешний ключ: {e}")
            
            # 6. Создать индексы
            print("\n6️⃣ Создание индексов...")
            try:
                await session.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_users_created_by_admin 
                    ON users(created_by_admin)
                """))
                await session.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_admins_username 
                    ON admins(username)
                """))
                print("   ✅ Индексы созданы")
            except Exception as e:
                print(f"   ⚠️ Ошибка создания индексов: {e}")
            
            # Коммит всех изменений
            await session.commit()
            
            # 7. Проверка результата
            print("\n7️⃣ Проверка результата...")
            result = await session.execute(text("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'users' 
                ORDER BY ordinal_position
            """))
            columns = result.fetchall()
            print("\n   Колонки таблицы users:")
            for col_name, col_type in columns:
                print(f"   - {col_name}: {col_type}")
            
            print("\n" + "=" * 60)
            print("✅ МИГРАЦИЯ ЗАВЕРШЕНА УСПЕШНО!")
            print("=" * 60)
            
        except Exception as e:
            print(f"\n❌ ОШИБКА МИГРАЦИИ: {e}")
            import traceback
            print(traceback.format_exc())
            await session.rollback()
            raise


if __name__ == "__main__":
    asyncio.run(run_migration())


