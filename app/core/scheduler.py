# app/core/scheduler.py
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.cleanup import cleanup_all_folders


def start_scheduler() -> BackgroundScheduler:
    """
    Запускает APScheduler в фоне и вешает задачу на 03:00 каждый день.
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

    scheduler.start()
    print("[SCHEDULER] Планировщик запущен, задача daily_folder_cleanup активна")
    return scheduler
