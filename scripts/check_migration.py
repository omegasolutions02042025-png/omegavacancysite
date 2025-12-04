"""Проверка миграции - проверяет наличие полей в БД"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.database import engine

async def check():
    async with AsyncSession(engine) as session:
        result = await session.execute(text("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'users' 
            AND column_name IN ('first_name', 'last_name', 'middle_name', 'phone', 'experience', 'specialization', 'resume')
            ORDER BY column_name
        """))
        cols = result.fetchall()
        
        output_file = Path(__file__).parent.parent / "migration_check_result.txt"
        with open(output_file, "w", encoding="utf-8") as f:
            if cols:
                f.write(f"Найдено {len(cols)} полей:\n")
                for col_name, col_type in cols:
                    f.write(f"  - {col_name} ({col_type})\n")
            else:
                f.write("Поля не найдены - миграция не выполнена\n")
        
        print(f"Результат сохранен в {output_file}")
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check())



