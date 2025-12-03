# app/core/passwords.py
"""
Модуль для хеширования и проверки паролей.

Использует pwdlib с рекомендуемой схемой Argon2 для безопасного хранения паролей.
"""
from pwdlib import PasswordHash

# Рекомендуемая схема (Argon2, без ограничения 72 байта)
pwd_hasher = PasswordHash.recommended()

def hash_password(password: str) -> str:
    """
    Захешировать пароль для безопасного хранения.
    
    Args:
        password: Пароль в открытом виде
        
    Returns:
        str: Хешированный пароль
    """
    return pwd_hasher.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Проверить соответствие пароля хешу.
    
    Args:
        plain_password: Пароль в открытом виде
        hashed_password: Хешированный пароль
        
    Returns:
        bool: True если пароль соответствует хешу, иначе False
    """
    return pwd_hasher.verify(plain_password, hashed_password)
