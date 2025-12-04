"""
Тестовый скрипт для проверки отображения ставок кандидатов
"""
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.database import engine, RecruiterCandidates
from app.services.currency_service import CandidateRateService, ExchangeRateService
from sqlmodel import select


async def test_currency_display():
    """Тест отображения валют для кандидатов"""
    
    async with AsyncSession(engine) as session:
        print("=" * 60)
        print("ТЕСТ ОТОБРАЖЕНИЯ СТАВОК КАНДИДАТОВ")
        print("=" * 60)
        
        # 1. Проверяем наличие курсов валют
        print("\n1. Проверка курсов валют...")
        exchange_rate = await ExchangeRateService.get_active_rate(session)
        
        if exchange_rate:
            print(f"✓ Активный курс найден:")
            print(f"  USD: {exchange_rate.usd_rate}")
            print(f"  EUR: {exchange_rate.eur_rate}")
            print(f"  BYN: {exchange_rate.byn_rate}")
            print(f"  Обновлено: {exchange_rate.fetched_at}")
        else:
            print("✗ Активный курс не найден!")
            return
        
        # 2. Получаем всех кандидатов
        print("\n2. Получение списка кандидатов...")
        query = select(RecruiterCandidates).limit(5)
        result = await session.execute(query)
        candidates = result.scalars().all()
        
        if not candidates:
            print("✗ Кандидаты не найдены в БД")
            return
        
        print(f"✓ Найдено кандидатов: {len(candidates)}")
        
        # 3. Проверяем отображение ставок
        print("\n3. Проверка отображения ставок:")
        print("-" * 60)
        
        for candidate in candidates:
            # Формируем имя
            name_parts = []
            if candidate.first_name:
                name_parts.append(candidate.first_name)
            if candidate.last_name:
                name_parts.append(candidate.last_name)
            full_name = " ".join(name_parts) if name_parts else "Без имени"
            
            print(f"\n👤 {full_name} (ID: {candidate.id})")
            print(f"   Должность: {candidate.title or 'Не указана'}")
            
            # Проверяем наличие ставки
            if candidate.base_rate_amount and candidate.base_rate_currency:
                print(f"   💰 Ставка ({candidate.rate_type or 'monthly'}):")
                print(f"      Базовая: {candidate.base_rate_amount} {candidate.base_rate_currency}")
                
                if candidate.rate_rub:
                    print(f"      ₽ {candidate.rate_rub:,.0f} RUB")
                if candidate.rate_usd:
                    print(f"      $ {candidate.rate_usd:,.0f} USD")
                if candidate.rate_eur:
                    print(f"      € {candidate.rate_eur:,.0f} EUR")
                if candidate.rate_byn:
                    print(f"      Br {candidate.rate_byn:,.0f} BYN")
                
                if candidate.rates_calculated_at:
                    print(f"      Рассчитано: {candidate.rates_calculated_at}")
            else:
                print(f"   ⚠️  Ставка не установлена")
        
        # 4. Тест пересчета ставки
        print("\n" + "=" * 60)
        print("4. Тест пересчета ставки для первого кандидата...")
        print("-" * 60)
        
        first_candidate = candidates[0]
        
        if first_candidate.base_rate_amount:
            print(f"Пересчитываем ставку для кандидата ID {first_candidate.id}...")
            
            updated = await CandidateRateService.recalculate_candidate_rates(
                session, first_candidate.id
            )
            
            if updated:
                print("✓ Ставка успешно пересчитана:")
                print(f"  ₽ {updated.rate_rub:,.2f} RUB")
                print(f"  $ {updated.rate_usd:,.2f} USD")
                print(f"  € {updated.rate_eur:,.2f} EUR")
                print(f"  Br {updated.rate_byn:,.2f} BYN")
            else:
                print("✗ Не удалось пересчитать ставку")
        else:
            print("⚠️  У первого кандидата нет ставки для пересчета")
            print("\nУстанавливаем тестовую ставку...")
            
            updated = await CandidateRateService.update_candidate_rate(
                session,
                first_candidate.id,
                base_amount=3000,
                base_currency="USD",
                rate_type="monthly"
            )
            
            if updated:
                print("✓ Тестовая ставка установлена:")
                print(f"  Базовая: {updated.base_rate_amount} {updated.base_rate_currency}")
                print(f"  ₽ {updated.rate_rub:,.2f} RUB")
                print(f"  $ {updated.rate_usd:,.2f} USD")
                print(f"  € {updated.rate_eur:,.2f} EUR")
                print(f"  Br {updated.rate_byn:,.2f} BYN")
            else:
                print("✗ Не удалось установить ставку")
        
        print("\n" + "=" * 60)
        print("ТЕСТ ЗАВЕРШЕН")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_currency_display())

