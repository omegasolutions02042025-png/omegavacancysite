"""
Простая миграция для добавления полей валют
"""
import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.core.config import settings


async def main():
    print("=" * 60)
    print("МИГРАЦИЯ: Добавление полей валют")
    print("=" * 60)
    
    engine = create_async_engine(settings.database_url, echo=False)
    
    async with engine.begin() as conn:
        # 1. Создаем таблицу exchange_rates
        print("\n1. Создание таблицы exchange_rates...")
        try:
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
            print("   ✓ Таблица создана")
        except Exception as e:
            print(f"   ✗ Ошибка: {e}")
        
        # Индексы
        try:
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_exchange_rates_fetched_at 
                ON exchange_rates(fetched_at)
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_exchange_rates_is_active 
                ON exchange_rates(is_active)
            """))
            print("   ✓ Индексы созданы")
        except Exception as e:
            print(f"   ✗ Ошибка индексов: {e}")
        
        # 2. Добавляем поля в candidate_profiles
        print("\n2. Добавление полей в candidate_profiles...")
        
        fields = [
            "base_rate_amount FLOAT",
            "base_rate_currency VARCHAR DEFAULT 'RUB'",
            "rate_type VARCHAR DEFAULT 'monthly'",
            "rate_rub FLOAT",
            "rate_usd FLOAT",
            "rate_eur FLOAT",
            "rate_byn FLOAT",
            "rates_calculated_at VARCHAR",
            "exchange_rate_snapshot_id INTEGER",
        ]
        
        for field_def in fields:
            field_name = field_def.split()[0]
            try:
                await conn.execute(text(f"""
                    ALTER TABLE candidate_profiles 
                    ADD COLUMN {field_def}
                """))
                print(f"   ✓ Добавлено: {field_name}")
            except Exception as e:
                if "already exists" in str(e) or "duplicate column" in str(e).lower():
                    print(f"   ⚠ Уже существует: {field_name}")
                else:
                    print(f"   ✗ Ошибка {field_name}: {e}")
    
    await engine.dispose()
    
    print("\n" + "=" * 60)
    print("МИГРАЦИЯ ЗАВЕРШЕНА")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

