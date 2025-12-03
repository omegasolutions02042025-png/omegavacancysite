"""
Миграция для добавления полей валют и курсов в базу данных
"""
import asyncio
import sys
from pathlib import Path

# Добавляем корневую директорию проекта в путь
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import text
from app.core.config import settings


async def run_migration():
    """Выполнить миграцию базы данных"""
    
    engine = create_async_engine(settings.database_url, echo=True)
    
    async with engine.begin() as conn:
        print("\n=== Начало миграции: добавление полей валют ===\n")
        
        # 1. Создаем таблицу exchange_rates
        print("1. Создание таблицы exchange_rates...")
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS exchange_rates (
                id SERIAL PRIMARY KEY,
                usd_rate FLOAT,
                eur_rate FLOAT,
                byn_rate FLOAT,
                fetched_at VARCHAR NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                last_update_status VARCHAR DEFAULT 'success',
                error_message VARCHAR
            )
        """))
        
        # Создаем индексы
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_exchange_rates_fetched_at 
            ON exchange_rates(fetched_at)
        """))
        
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_exchange_rates_is_active 
            ON exchange_rates(is_active)
        """))
        
        print("✓ Таблица exchange_rates создана\n")
        
        # 2. Добавляем поля в таблицу candidate_profiles
        print("2. Добавление полей валют в candidate_profiles...")
        
        fields_to_add = [
            ("base_rate_amount", "FLOAT"),
            ("base_rate_currency", "VARCHAR DEFAULT 'RUB'"),
            ("rate_type", "VARCHAR DEFAULT 'monthly'"),
            ("rate_rub", "FLOAT"),
            ("rate_usd", "FLOAT"),
            ("rate_eur", "FLOAT"),
            ("rate_byn", "FLOAT"),
            ("rates_calculated_at", "VARCHAR"),
            ("exchange_rate_snapshot_id", "INTEGER"),
        ]
        
        for field_name, field_type in fields_to_add:
            try:
                # Проверяем существование колонки
                check_query = text("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name='candidate_profiles' 
                    AND column_name=:col_name
                """)
                result = await conn.execute(check_query, {"col_name": field_name})
                exists = result.fetchone() is not None
                
                if not exists:
                    await conn.execute(text(f"""
                        ALTER TABLE candidate_profiles 
                        ADD COLUMN {field_name} {field_type}
                    """))
                    print(f"  ✓ Добавлено поле: {field_name}")
                else:
                    print(f"  ⚠ Поле {field_name} уже существует")
            except Exception as e:
                print(f"  ❌ Ошибка при добавлении {field_name}: {e}")
        
        print("\n=== Миграция завершена успешно! ===\n")
    
    await engine.dispose()


if __name__ == "__main__":
    print("Запуск миграции для добавления полей валют...")
    asyncio.run(run_migration())
    print("\nГотово!")

