@echo off
REM Скрипт для применения миграций Alembic
REM Использование: apply_migration.bat [команда]
REM Примеры:
REM   apply_migration.bat upgrade head
REM   apply_migration.bat current
REM   apply_migration.bat history

if "%1"=="" (
    echo Применение всех миграций...
    call venv\Scripts\alembic.exe upgrade head
) else (
    call venv\Scripts\alembic.exe %*
)




