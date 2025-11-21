# app/core/redis_tasks.py

import os
import json
from typing import Any, Optional

from redis.asyncio import Redis

# Можно вынести в Settings, пока так
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

redis: Redis = Redis.from_url(
    REDIS_URL,
    decode_responses=True,  # сразу строки, а не bytes
)

TASK_KEY_PREFIX = "sverka_task:"
TASK_TTL_SECONDS = 60 * 60  # 1 час хранения задач


async def set_task(task_id: str, data: dict[str, Any]) -> None:
    """
    Сохраняем/обновляем задачу сверки в Redis.
    """
    key = f"{TASK_KEY_PREFIX}{task_id}"
    await redis.set(
        key,
        json.dumps(data, ensure_ascii=False),
        ex=TASK_TTL_SECONDS,
    )


async def get_task(task_id: str) -> Optional[dict[str, Any]]:
    """
    Получаем задачу сверки из Redis.
    """
    key = f"{TASK_KEY_PREFIX}{task_id}"
    raw = await redis.get(key)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # на всякий случай, чтобы не ронять ручку
        return None


async def delete_task(task_id: str) -> None:
    """
    Удаляем задачу после использования (если нужно).
    """
    key = f"{TASK_KEY_PREFIX}{task_id}"
    await redis.delete(key)
