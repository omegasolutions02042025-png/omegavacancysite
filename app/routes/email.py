from os import curdir
from fastapi import APIRouter, Form, Depends
from app.core.current_user import get_current_user_from_cookie
from app.database.user_db import UserRepository
from pydantic import EmailStr
from fastapi import HTTPException, status
from app.core.email_send import send_email_smtp
from fastapi.responses import JSONResponse
from app.core.email_listener import email_listener



user_repo = UserRepository()

router = APIRouter(prefix="/email", tags=["Email"])


USER_EMAIL : dict[int, str] = {}

@router.post("/connect")
async def connect_email(email: EmailStr = Form(...),current_user=Depends(get_current_user_from_cookie),):
    if not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Необходима авторизация")
    
    USER_EMAIL[current_user.id] = email


    return JSONResponse(
        {
            "ok": True,
            "message": "Введите пароль приложения почтового сервиса",
            "email": email,
        }
    )

@router.post("/password")
async def connect_email_password(password: str = Form(...),current_user=Depends(get_current_user_from_cookie),):
    if not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Необходима авторизация")

    email = USER_EMAIL[current_user.id]
    print(email)
    success = await send_email_smtp(
        sender_email=email,
        recipient_email=email,
        subject="Подтверждение привязки email",
        body="Вы успешно привязали email к аккаунту",
        html=True,
        smtp_host='mailbe07.hoster.by', 
        smtp_port=465,
        smtp_username=email,
        smtp_password=password,
        use_tls=True,
        use_starttls=False,
    )
    if success:
        await user_repo.update_user_email(current_user.id, email, password)
        await email_listener.restart_for_user(current_user.id)
        del USER_EMAIL[current_user.id]
        return JSONResponse(
            {
                "ok": True,
                "message": "Email успешно привязан",
                "email": email,
            }
        )
    else:
        del USER_EMAIL[current_user.id]
        return JSONResponse(
            {
                "ok": False,
                "message": "Не удалось привязать email",
                "email": email,
            }
        )
    
    
@router.post("/unlink")
async def unlink_email(current_user=Depends(get_current_user_from_cookie)):
    if not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Необходима авторизация")
    await user_repo.update_user_email(current_user.id, None, None)
    await email_listener.stop_for_user(current_user.id)
    return JSONResponse(
        {
            "ok": True,
            "message": "Email успешно отвязан",
        }
    )

    
