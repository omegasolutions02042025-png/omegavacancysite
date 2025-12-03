# app/core/scheduler.py
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import asyncio

from app.core.cleanup import cleanup_all_folders


def update_exchange_rates_job():
    """
    Синхронная обертка для асинхронного обновления курсов валют
    """
    from app.database.database import get_db
    from app.services.currency_service import CurrencyService
    
    async def _update():
        async for session in get_db():
            try:
                await CurrencyService.update_exchange_rates(session)
                print("[SCHEDULER] Курсы валют успешно обновлены")
            except Exception as e:
                print(f"[SCHEDULER] Ошибка обновления курсов: {e}")
            break
    
    # Запускаем асинхронную функцию в новом event loop
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_update())
        loop.close()
    except Exception as e:
        print(f"[SCHEDULER] Критическая ошибка при обновлении курсов: {e}")


def start_scheduler() -> BackgroundScheduler:
    """
    Запускает APScheduler в фоне и вешает задачи на выполнение по расписанию.
    """
    # Можно поменять таймзону, если нужно
    scheduler = BackgroundScheduler(timezone="Europe/Moscow")

    # Задача: каждый день в 03:00 вызывать cleanup_all_folders
    scheduler.add_job(
        cleanup_all_folders,
        trigger=CronTrigger(hour=3, minute=0),
        id="daily_folder_cleanup",
        replace_existing=True,
    )
    
    # Задача: каждый день в 09:00 обновлять курсы валют
    scheduler.add_job(
        update_exchange_rates_job,
        trigger=CronTrigger(hour=9, minute=0),
        id="daily_exchange_rates_update",
        replace_existing=True,
    )

    scheduler.start()
    print("[SCHEDULER] Планировщик запущен")
    print("[SCHEDULER] - daily_folder_cleanup: каждый день в 03:00")
    print("[SCHEDULER] - daily_exchange_rates_update: каждый день в 09:00")
    return scheduler
