# app/core/cleanup.py
import shutil
from pathlib import Path
from datetime import datetime

# 👉 сюда впиши свои реальные пути
FOLDERS_TO_DELETE = [
    r"C:\Users\Administrator\Desktop\omegavacsite\app\resumes"
]


def delete_folder(folder_path: str) -> None:
    """
    Удаляет папку вместе со всем содержимым.
    Ничего не делает, если папка не существует.
    """
    path = Path(folder_path).resolve()

    # Защита от удаления корня диска (C:\, D:\ и т.п.)
    if path == path.anchor:
        raise ValueError(f"Опасная операция: попытка удалить корень диска: {path}")

    if path.exists() and path.is_dir():
        shutil.rmtree(path)
        print(f"[OK] {datetime.now()} Папка удалена: {path}")
    else:
        print(f"[SKIP] {datetime.now()} Папка не найдена: {path}")


def cleanup_all_folders() -> None:
    """
    Проходит по списку FOLDERS_TO_DELETE и удаляет каждую папку.
    """
    print(f"[{datetime.now()}] Старт ежедневной очистки")
    for folder in FOLDERS_TO_DELETE:
        try:
            delete_folder(folder)
        except Exception as e:
            print(f"[ERR] Ошибка при удалении {folder}: {e}")
