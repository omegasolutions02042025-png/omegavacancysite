# app/core/passwords.py
from pwdlib import PasswordHash

# Рекомендуемая схема (Argon2, без ограничения 72 байта)
pwd_hasher = PasswordHash.recommended()

def hash_password(password: str) -> str:
    return pwd_hasher.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_hasher.verify(plain_password, hashed_password)
