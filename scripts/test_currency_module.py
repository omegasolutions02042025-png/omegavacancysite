"""
Тестовый скрипт для проверки работы модуля валют
"""
import asyncio
import sys
from pathlib import Path

# Добавляем корневую директорию проекта в путь
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from app.core.config import settings
from app.core.exchange_rate_parser import parse_cb_rf
from app.services.currency_service import ExchangeRateService, CurrencyService


async def test_parser():
    """Тест парсера курсов ЦБ РФ"""
    print("\n" + "="*60)
    print("ТЕСТ 1: Парсер курсов ЦБ РФ")
    print("="*60)
    
    rates = parse_cb_rf()
    
    if rates:
        print("✅ Парсер работает!")
        print(f"   USD: {rates['USD']:.4f} RUB")
        print(f"   EUR: {rates['EUR']:.4f} RUB")
        print(f"   BYN: {rates['BYN']:.4f} RUB")
        return True
    else:
        print("❌ Ошибка парсера!")
        return False


async def test_database_operations():
    """Тест операций с БД"""
    print("\n" + "="*60)
    print("ТЕСТ 2: Операции с базой данных")
    print("="*60)
    
    engine = create_async_engine(settings.database_url, echo=False)
    
    async with AsyncSession(engine) as session:
        # Получаем курсы
        rates = parse_cb_rf()
        
        if not rates:
            print("❌ Не удалось получить курсы для теста")
            return False
        
        # Создаем запись
        print("\n📝 Создание записи с курсами...")
        new_rate = await ExchangeRateService.create_rate(
            session,
            usd_rate=rates['USD'],
            eur_rate=rates['EUR'],
            byn_rate=rates['BYN']
        )
        
        if new_rate:
            print(f"✅ Запись создана (ID: {new_rate.id})")
            print(f"   Время: {new_rate.fetched_at}")
            print(f"   Активна: {new_rate.is_active}")
        else:
            print("❌ Ошибка создания записи")
            return False
        
        # Получаем активный курс
        print("\n📊 Получение активного курса...")
        active_rate = await ExchangeRateService.get_active_rate(session)
        
        if active_rate:
            print(f"✅ Активный курс найден (ID: {active_rate.id})")
            print(f"   USD: {active_rate.usd_rate:.4f}")
            print(f"   EUR: {active_rate.eur_rate:.4f}")
            print(f"   BYN: {active_rate.byn_rate:.4f}")
        else:
            print("❌ Активный курс не найден")
            return False
    
    await engine.dispose()
    return True


async def test_currency_conversion():
    """Тест конвертации валют"""
    print("\n" + "="*60)
    print("ТЕСТ 3: Конвертация валют")
    print("="*60)
    
    engine = create_async_engine(settings.database_url, echo=False)
    
    async with AsyncSession(engine) as session:
        # Получаем активный курс
        exchange_rate = await ExchangeRateService.get_active_rate(session)
        
        if not exchange_rate:
            print("❌ Активный курс не найден")
            return False
        
        # Тест 1: USD → RUB
        print("\n💱 Конвертация 1000 USD → RUB")
        amount_rub = CurrencyService.convert_to_rub(1000, "USD", exchange_rate)
        print(f"   Результат: {amount_rub:.2f} RUB")
        
        # Тест 2: RUB → EUR
        print("\n💱 Конвертация 100000 RUB → EUR")
        amount_eur = CurrencyService.convert_from_rub(100000, "EUR", exchange_rate)
        print(f"   Результат: {amount_eur:.2f} EUR")
        
        # Тест 3: Расчет во всех валютах
        print("\n💱 Расчет ставки 3000 USD во всех валютах")
        all_rates = CurrencyService.calculate_all_rates(3000, "USD", exchange_rate)
        print(f"   RUB: {all_rates['RUB']:.2f}")
        print(f"   USD: {all_rates['USD']:.2f}")
        print(f"   EUR: {all_rates['EUR']:.2f}")
        print(f"   BYN: {all_rates['BYN']:.2f}")
        
        print("\n✅ Все конвертации выполнены успешно!")
    
    await engine.dispose()
    return True


async def test_service_update():
    """Тест обновления курсов через сервис"""
    print("\n" + "="*60)
    print("ТЕСТ 4: Обновление курсов через сервис")
    print("="*60)
    
    engine = create_async_engine(settings.database_url, echo=False)
    
    async with AsyncSession(engine) as session:
        print("\n🔄 Обновление курсов...")
        new_rate = await CurrencyService.update_exchange_rates(session)
        
        if new_rate:
            print(f"✅ Курсы обновлены (ID: {new_rate.id})")
            print(f"   USD: {new_rate.usd_rate:.4f}")
            print(f"   EUR: {new_rate.eur_rate:.4f}")
            print(f"   BYN: {new_rate.byn_rate:.4f}")
            print(f"   Статус: {new_rate.last_update_status}")
            return True
        else:
            print("❌ Ошибка обновления курсов")
            return False
    
    await engine.dispose()


async def test_ensure_rates():
    """Тест проверки доступности курсов"""
    print("\n" + "="*60)
    print("ТЕСТ 5: Проверка доступности курсов")
    print("="*60)
    
    engine = create_async_engine(settings.database_url, echo=False)
    
    async with AsyncSession(engine) as session:
        print("\n🔍 Проверка наличия курсов...")
        available = await CurrencyService.ensure_rates_available(session)
        
        if available:
            print("✅ Курсы доступны!")
            return True
        else:
            print("❌ Курсы недоступны")
            return False
    
    await engine.dispose()


async def run_all_tests():
    """Запуск всех тестов"""
    print("\n" + "="*60)
    print("ТЕСТИРОВАНИЕ МОДУЛЯ ВАЛЮТ")
    print("="*60)
    
    results = []
    
    # Тест 1: Парсер
    try:
        result = await test_parser()
        results.append(("Парсер курсов", result))
    except Exception as e:
        print(f"❌ Ошибка в тесте парсера: {e}")
        results.append(("Парсер курсов", False))
    
    # Тест 2: БД операции
    try:
        result = await test_database_operations()
        results.append(("Операции с БД", result))
    except Exception as e:
        print(f"❌ Ошибка в тесте БД: {e}")
        results.append(("Операции с БД", False))
    
    # Тест 3: Конвертация
    try:
        result = await test_currency_conversion()
        results.append(("Конвертация валют", result))
    except Exception as e:
        print(f"❌ Ошибка в тесте конвертации: {e}")
        results.append(("Конвертация валют", False))
    
    # Тест 4: Обновление через сервис
    try:
        result = await test_service_update()
        results.append(("Обновление курсов", result))
    except Exception as e:
        print(f"❌ Ошибка в тесте обновления: {e}")
        results.append(("Обновление курсов", False))
    
    # Тест 5: Проверка доступности
    try:
        result = await test_ensure_rates()
        results.append(("Проверка доступности", result))
    except Exception as e:
        print(f"❌ Ошибка в тесте доступности: {e}")
        results.append(("Проверка доступности", False))
    
    # Итоги
    print("\n" + "="*60)
    print("ИТОГИ ТЕСТИРОВАНИЯ")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    print("\n" + "-"*60)
    print(f"Пройдено: {passed}/{total}")
    print(f"Успешность: {(passed/total*100):.1f}%")
    print("="*60)
    
    if passed == total:
        print("\n🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
        print("Модуль валют готов к использованию.")
    else:
        print("\n⚠️  НЕКОТОРЫЕ ТЕСТЫ НЕ ПРОЙДЕНЫ")
        print("Проверьте ошибки выше.")
    
    return passed == total


if __name__ == "__main__":
    print("Запуск тестов модуля валют...")
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)

