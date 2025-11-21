# app/routes/notifications.py
from fastapi import APIRouter, Depends
from app.database.user_db import UserRepository
from app.core.current_user import get_current_user_from_cookie
from pydantic import BaseModel

router = APIRouter(tags=["notifications"])
user_repo = UserRepository()


class DeleteNotificationPayload(BaseModel):
    notification: str


@router.get("/api/get_notif")
async def get_notif(current_user = Depends(get_current_user_from_cookie)):
    """
    Вернёт список уведомлений для текущего пользователя.
    В БД хранится только текст, но мы дополнительно отдаём id.
    """
    if not current_user:
        return []

    rows = await user_repo.get_user_notifications(current_user.id)
    # rows — список UserNotification
    return [
        {
            "id": n.id,                      # если пригодится на фронте
            "notification": n.notification,  # сам текст
            "url": n.url
        }
        for n in rows
    ]


@router.post("/api/del_notif")
async def del_notif(
    payload: DeleteNotificationPayload,
    current_user = Depends(get_current_user_from_cookie),
):
    """
    Удаляет уведомление по тексту (как у тебя в репозитории).
    """
    if not current_user:
        return {"ok": False}

    await user_repo.delete_user_notification(
        user_id=current_user.id,
        notification=payload.notification,
    )
    return {"ok": True}
