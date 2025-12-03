"""
Скрипт для выполнения миграции добавления полей профиля рекрутера
"""
import asyncio
import sys
from pathlib import Path

# Добавляем корневую директорию проекта в путь
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from app.database.database import engine


async def run_migration():
    """Выполнить миграцию для добавления полей профиля рекрутера"""
    
    migration_sql = """
    -- Добавить новые колонки для профиля рекрутера
    ALTER TABLE users 
    ADD COLUMN IF NOT EXISTS first_name VARCHAR,
    ADD COLUMN IF NOT EXISTS last_name VARCHAR,
    ADD COLUMN IF NOT EXISTS middle_name VARCHAR,
    ADD COLUMN IF NOT EXISTS phone VARCHAR,
    ADD COLUMN IF NOT EXISTS experience TEXT,
    ADD COLUMN IF NOT EXISTS specialization VARCHAR,
    ADD COLUMN IF NOT EXISTS resume TEXT;

    -- Создать индексы для поиска по имени и фамилии
    CREATE INDEX IF NOT EXISTS idx_users_first_name ON users(first_name);
    CREATE INDEX IF NOT EXISTS idx_users_last_name ON users(last_name);
    CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone);
    """
    
    try:
        print("Начинаю выполнение миграции...", flush=True)
        sys.stdout.flush()
        
        async with engine.begin() as conn:
            # Выполняем SQL команды по отдельности
            commands = [
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS first_name VARCHAR",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_name VARCHAR",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS middle_name VARCHAR",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS phone VARCHAR",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS experience TEXT",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS specialization VARCHAR",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS resume TEXT",
                "CREATE INDEX IF NOT EXISTS idx_users_first_name ON users(first_name)",
                "CREATE INDEX IF NOT EXISTS idx_users_last_name ON users(last_name)",
                "CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone)",
            ]
            
            for cmd in commands:
                try:
                    await conn.execute(text(cmd))
                    print(f"Выполнено: {cmd[:50]}...", flush=True)
                except Exception as e:
                    # Игнорируем ошибки если колонка уже существует
                    if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                        print(f"Пропущено (уже существует): {cmd[:50]}...", flush=True)
                    else:
                        print(f"Ошибка при выполнении '{cmd[:50]}...': {e}", flush=True)
                        raise
        
        # Проверяем результат
        async with engine.connect() as conn:
            result = await conn.execute(text("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'users' 
                AND column_name IN ('first_name', 'last_name', 'middle_name', 'phone', 'experience', 'specialization', 'resume')
                ORDER BY ordinal_position
            """))
            columns = result.fetchall()
            
            if columns:
                print("\nМиграция успешно выполнена! Добавлены следующие поля:", flush=True)
                for col_name, col_type in columns:
                    print(f"   - {col_name} ({col_type})", flush=True)
            else:
                print("\nПоля не найдены в таблице users", flush=True)
        
        print("\nМиграция завершена успешно!", flush=True)
        
    except Exception as e:
        print(f"\nОшибка при выполнении миграции: {e}", flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run_migration())

