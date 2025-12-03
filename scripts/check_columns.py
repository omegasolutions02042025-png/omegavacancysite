import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.core.config import settings


async def main():
    engine = create_async_engine(settings.database_url, echo=False)
    
    async with engine.begin() as conn:
        result = await conn.execute(text("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name='candidate_profiles'
            ORDER BY ordinal_position
        """))
        
        columns = result.fetchall()
        
        print("\nКолонки в таблице candidate_profiles:")
        print("-" * 50)
        for col in columns:
            print(f"{col[0]:40} {col[1]}")
        
        # Проверяем наличие нужных колонок
        col_names = [col[0] for col in columns]
        
        print("\n" + "=" * 50)
        print("Проверка полей валют:")
        print("=" * 50)
        
        currency_fields = [
            'base_rate_amount',
            'base_rate_currency',
            'rate_type',
            'rate_rub',
            'rate_usd',
            'rate_eur',
            'rate_byn',
            'rates_calculated_at',
            'exchange_rate_snapshot_id'
        ]
        
        for field in currency_fields:
            status = "✓" if field in col_names else "✗"
            print(f"{status} {field}")
    
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

