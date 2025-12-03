# app/core/security/auth.py
from authx import AuthX, AuthXConfig
from app.core.config import settings
config = AuthXConfig(
    JWT_ALGORITHM="HS256",
    JWT_SECRET_KEY=settings.jwt_secret_key,
    JWT_ACCESS_TOKEN_EXPIRES=60 * 60 * 24,        # 24 часа
    JWT_REFRESH_TOKEN_EXPIRES=60 * 60 * 24 * 30, # 30 дней
)
config.JWT_TOKEN_LOCATION = ["cookies"]  # или ["headers", "cookies"], если захочешь оба варианта

# 🔹 Имя cookie, где лежит access token
config.JWT_ACCESS_COOKIE_NAME = "access_token"

# На локалхосте обычно надо отключить secure, иначе браузер не пришлёт cookie по http
config.JWT_COOKIE_SECURE = False

# На время отладки удобно выключить CSRF-проверку, чтобы не ловить ошибку Missing CSRF token
config.JWT_COOKIE_CSRF_PROTECT = False


auth = AuthX(config)
