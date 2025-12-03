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
from app.core.email_send import send_email_smtp
from app.database.user_db import UserRepository
from app.database.chat_db import chat_repository
from app.database.vacancy_db import VacancyRepository
from app.core.telethon_check import manager

router = APIRouter()
user_repo = UserRepository()
vacancy_repo = VacancyRepository()

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
    entity = await send_message_by_username('@Halinakazz',message, client)
    await client.disconnect()

    if not entity:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Не удалось отправить сообщение")
    
    await user_repo.create_user_comunication(user_id=current_user.id,
                                            email_user=None,
                                            telegram_user_id=entity.id,
                                            vacancy_id=vac_id,
                                            candidate_fullname=candidate_fullname)
    
    # Получаем название вакансии
    vacancy_title = None
    if vac_id:
        vacancy = await vacancy_repo.get_vacancy_by_id(vac_id)
        if vacancy:
            vacancy_title = vacancy.title
    
    # Получаем ID кандидата
    from app.database.candidate_db import CandidateRepository
    candidate_repo = CandidateRepository()
    candidate_id = await candidate_repo.get_candidate_id_by_fullname(
        user_id=current_user.id,
        candidate_fullname=candidate_fullname
    )
    
    # Сохраняем сообщение в чат
    try:
        await chat_repository.add_message(
            user_id=current_user.id,
            candidate_id=candidate_id,
            candidate_fullname=candidate_fullname,
            vacancy_id=vac_id,
            message_type="telegram",
            sender="user",
            message_text=message,
            vacancy_title=vacancy_title,
        )
    except Exception as e:
        print(f"[SEND_TELEGRAM] Ошибка сохранения в чат: {e}")
    
    await manager.restart_session(current_user.id)
    return JSONResponse(
        {
            "ok": True,
            "message": f"Сообщение отправлено {candidate_fullname}",
        }
    )


@router.post("/api/send/email")
async def send_email_api(payload: SendMail, current_user = Depends(get_current_user_from_cookie)):
    import sys
    print(f"\n{'='*80}", flush=True)
    print(f"[SEND_EMAIL_API] 🚀 РУЧКА ВЫЗВАНА! Начало отправки email", flush=True)
    print(f"[SEND_EMAIL_API] Current user: {current_user.email if current_user else None}", flush=True)
    sys.stdout.flush()
    
    if not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Необходима авторизация")
    
    vac_id = payload.vacancy_id
    candidate_fullname = payload.candidate_fullname
    contact = payload.contact
    message = payload.message
    
    print(f"[SEND_EMAIL_API] Кандидат: {candidate_fullname}", flush=True)
    print(f"[SEND_EMAIL_API] Контакт: {contact}", flush=True)
    print(f"[SEND_EMAIL_API] Вакансия: {vac_id}", flush=True)
    print(f"[SEND_EMAIL_API] Длина сообщения: {len(message)}", flush=True)
    
    app_pass = current_user.work_email_app_pass
    work_email = current_user.work_email

    if not app_pass:
        print(f"[SEND_EMAIL_API] ❌ Нет app_pass для {work_email}", flush=True)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Привяжите email к аккаунту")
    
    if not work_email:
        print(f"[SEND_EMAIL_API] ❌ Нет work_email", flush=True)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Укажите рабочий email")
    
    print(f"[SEND_EMAIL_API] Work email: {work_email}", flush=True)
    print(f"[SEND_EMAIL_API] App pass: {'*' * len(app_pass)}", flush=True)
    
    subject = f"Здравствуйте, {candidate_fullname}. Я представитель компании Omega Solutions"
    recipient = 'artursimoncik@gmail.com'
    
    print(f"[SEND_EMAIL_API] Отправка на: {recipient}", flush=True)
    print(f"[SEND_EMAIL_API] Тема: {subject}", flush=True)
    
    
    try:
        success = await send_email_smtp(
            sender_email=work_email,
            recipient_email=recipient,
            subject=subject,
            body=message,
            html=True,  # ✅ Явно указываем html=True
            smtp_host='mailbe07.hoster.by',
            smtp_port=465,
            smtp_username=work_email,
            smtp_password=app_pass,
            use_tls=True,
            use_starttls=False,
        )
        
        print(f"[SEND_EMAIL_API] Результат отправки: {success}", flush=True)
        
    except Exception as e:
        print(f"[SEND_EMAIL_API] ❌ Исключение при отправке: {e}", flush=True)
        import traceback
        print(f"[SEND_EMAIL_API] Traceback:\n{traceback.format_exc()}", flush=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка отправки email: {str(e)}"
        )
    
    if not success:
        print(f"[SEND_EMAIL_API] ❌ Отправка не удалась (success=False)", flush=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось отправить сообщение. Проверьте настройки email."
        )

    print(f"[SEND_EMAIL_API] ✅ Email успешно отправлен!", flush=True)
    
    # Сохраняем коммуникацию
    try:
        await user_repo.create_user_comunication(
            user_id=current_user.id,
            email_user=recipient,
            telegram_user_id=None,
            vacancy_id=vac_id,
            candidate_fullname=candidate_fullname
        )
        print(f"[SEND_EMAIL_API] ✅ Коммуникация сохранена в БД", flush=True)
    except Exception as e:
        print(f"[SEND_EMAIL_API] ⚠️ Ошибка сохранения коммуникации: {e}", flush=True)
    
    # Получаем название вакансии
    vacancy_title = None
    if vac_id:
        try:
            vacancy = await vacancy_repo.get_vacancy_by_id(vac_id)
            if vacancy:
                vacancy_title = vacancy.title
                print(f"[SEND_EMAIL_API] Название вакансии: {vacancy_title}", flush=True)
        except Exception as e:
            print(f"[SEND_EMAIL_API] ⚠️ Ошибка получения вакансии: {e}", flush=True)
    
    # Получаем ID кандидата
    from app.database.candidate_db import CandidateRepository
    candidate_repo = CandidateRepository()
    candidate_id = await candidate_repo.get_candidate_id_by_fullname(
        user_id=current_user.id,
        candidate_fullname=candidate_fullname
    )
    
    # Сохраняем сообщение в чат
    try:
        saved_message = await chat_repository.add_message(
            user_id=current_user.id,
            candidate_id=candidate_id,
            candidate_fullname=candidate_fullname,
            vacancy_id=vac_id,
            message_type="email",
            sender="user",
            message_text=message,
            vacancy_title=vacancy_title,
        )
        print(f"[SEND_EMAIL_API] ✅ Сообщение сохранено в чат с ID: {saved_message.id}", flush=True)
    except Exception as e:
        print(f"[SEND_EMAIL_API] ⚠️ Ошибка сохранения в чат: {e}", flush=True)
        import traceback
        print(f"[SEND_EMAIL_API] Traceback:\n{traceback.format_exc()}", flush=True)

    print(f"[SEND_EMAIL_API] ✅ Все операции завершены успешно", flush=True)
    print(f"{'='*80}\n", flush=True)
    
    return JSONResponse(
        {
            "ok": True,
            "message": f"Сообщение отправлено {candidate_fullname}",
        }
    )
