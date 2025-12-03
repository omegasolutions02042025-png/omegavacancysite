"""Проверка наличия полей профиля рекрутера в БД"""
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
        
        output = []
        output.append("=" * 60)
        output.append("ПРОВЕРКА ПОЛЕЙ ПРОФИЛЯ РЕКРУТЕРА")
        output.append("=" * 60)
        
        if cols:
            output.append(f"\nНайдено {len(cols)} полей:")
            for col_name, col_type in cols:
                output.append(f"  ✅ {col_name} ({col_type})")
        else:
            output.append("\n❌ Поля не найдены - миграция не выполнена")
        
        output.append("\n" + "=" * 60)
        
        result_text = "\n".join(output)
        print(result_text)
        
        # Сохраняем в файл
        output_file = Path(__file__).parent.parent / "check_result.txt"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(result_text)
        
        print(f"\nРезультат сохранен в: {output_file}")
        
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check())


