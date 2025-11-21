from tkinter import S
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from app.core.current_user import get_current_user_from_cookie
from app.core.utils import send_message_by_username
from fastapi import HTTPException, status
from fastapi import Form
from telethon import TelegramClient
from app.core.config import settings
from app.models.send_mail import SendMail
from app.core.email_send import send_email_gmail
from app.database.user_db import UserRepository
from app.core.telethon_check import manager

router = APIRouter()
user_repo = UserRepository()

@router.post("/api/send/telegram")
async def send_telegram(payload: SendMail, current_user = Depends(get_current_user_from_cookie)):
    if not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Необходима авторизация")

    vac_id = payload.vacancy_id
    candidate_fullname = payload.candidate_fullname
    contact = payload.contact
    message = payload.message
    print(contact)

    session =f'sessions/{current_user.work_telegram_session_name}'
    api_id = settings.api_id
    api_hash = settings.api_hash
    client : TelegramClient = await manager.get_client(current_user.id)
    if not client.is_connected():
        await client.connect()

    if not await client.is_user_authorized():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Необходима авторизация")
    entity = await send_message_by_username('@kupitmancik',message, client)
    await client.disconnect()
    if not entity:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Не удалось отправить сообщение")
    
    await user_repo.create_user_comunication(user_id=current_user.id,
                                            email_user=None,
                                            telegram_user_id=entity.id,
                                            vacancy_id=vac_id,
                                            candidate_fullname=candidate_fullname)
    await manager.restart_session(current_user.id)
    return JSONResponse(
        {
            "ok": True,
            "message": f"Сообщение отправлено {candidate_fullname}",
        }
    )


@router.post("/api/send/email")
async def send_email(payload: SendMail, current_user = Depends(get_current_user_from_cookie)):
    if not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Необходима авторизация")
    
    vac_id = payload.vacancy_id
    candidate_fullname = payload.candidate_fullname
    contact = payload.contact
    message = payload.message
    print(contact)
    
    app_pass = current_user.work_email_app_pass
    if not app_pass:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Необходима авторизация")
    print(app_pass)
    subject = f"Здравствуйте, {candidate_fullname}. Я представитель компании Omega Solutions"
    work_email = current_user.work_email
    print(work_email)
    success = await send_email_gmail(
        sender_email=work_email,
        app_password=app_pass,
        recipient_email='artursimoncik@gmail.com',
        subject=subject,
        body=message,
        
    )
    if not success:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Не удалось отправить сообщение")

    await user_repo.create_user_comunication(user_id=current_user.id,
                                            email_user=contact,
                                            telegram_user_id=None,
                                            vacancy_id=vac_id,
                                            candidate_fullname=candidate_fullname)

    return JSONResponse(
        {
            "ok": True,
            "message": f"Сообщение отправлено {candidate_fullname}",
        }
    )
