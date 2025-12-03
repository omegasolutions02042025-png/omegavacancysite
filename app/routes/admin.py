from fastapi import APIRouter, Depends, Form, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from typing import Annotated
import secrets
import string
import jwt
from datetime import datetime, timedelta

from app.core.security import auth as authx, config
from app.core.current_user import get_current_user_from_cookie
from app.database.admin_db import admin_repository
from app.database.registration_db import registration_repository
from app.database.chat_db import chat_repository
from app.core.email_send import send_email_smtp
from app.core.config import settings

router = APIRouter(prefix="/admin", tags=["Администрирование"])
templates_dir = str(Path(__file__).resolve().parent.parent / "templates")
templates = Jinja2Templates(directory=templates_dir)



async def get_current_admin_from_cookie(request: Request):
    """
    Получить текущего администратора из cookie с токеном доступа.
    
    Декодирует JWT токен из cookie и проверяет существование администратора в БД.
    
    Args:
        request: FastAPI Request объект
        
    Returns:
        dict: Словарь с id и username администратора или None если не авторизован
    """
    token = request.cookies.get("admin_access_token")
    if not token:
        return None
    
    try:
        # Декодируем токен используя jwt напрямую
        payload = jwt.decode(
            token,
            config.JWT_SECRET_KEY,
            algorithms=[config.JWT_ALGORITHM],
        )
        
        admin_id = payload.get("sub")
        if not admin_id:
            return None
        
        admin_id = int(admin_id)
        
        # Проверяем что администратор существует
        admin = await admin_repository.get_by_id(admin_id)
        if not admin:
            return None
        
        return {"id": admin_id, "username": admin.username}
    except jwt.PyJWTError:
        return None
    except Exception:
        return None


def generate_password(length=12):
    """
    Генерация случайного пароля для рекрутеров.
    
    Args:
        length: Длина пароля (по умолчанию 12 символов)
        
    Returns:
        str: Случайный пароль из букв, цифр и специальных символов
    """
    characters = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(secrets.choice(characters) for _ in range(length))


@router.get("/login", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    """
    Страница входа для администратора.
    
    Args:
        request: FastAPI Request объект
        
    Returns:
        HTMLResponse: HTML страница входа администратора
    """
    return templates.TemplateResponse("admin/login.html", {"request": request})


@router.post("/login")
async def admin_login(
    username: str = Form(...),
    password: str = Form(...)
):
    """
    Аутентификация администратора.
    
    Проверяет учетные данные и создает JWT токен для доступа.
    
    Args:
        username: Имя пользователя администратора
        password: Пароль администратора
        
    Returns:
        RedirectResponse: Редирект на панель администратора с установленной cookie
        
    Raises:
        HTTPException: Если учетные данные неверны
    """
    admin = await admin_repository.authenticate(username, password)
    if not admin:
        raise HTTPException(status_code=400, detail="Неверный логин или пароль")
    
    # Создаем токен и устанавливаем cookie
    token = authx.create_access_token(uid=str(admin.id))
    
    response = RedirectResponse("/admin/dashboard", status_code=303)
    response.set_cookie(
        "admin_access_token",
        token,
        httponly=True,
        samesite="lax",
        path="/"
    )
    
    return response


@router.get("/dashboard", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    current_admin=Depends(get_current_admin_from_cookie)
):
    """
    Главная панель администратора.
    
    Отображает список всех рекрутеров и количество заявок на регистрацию.
    
    Args:
        request: FastAPI Request объект
        current_admin: Текущий администратор (из cookie)
        
    Returns:
        HTMLResponse: HTML страница панели администратора или редирект на логин
    """
    if not current_admin:
        return RedirectResponse("/admin/login", status_code=303)
    
    # Получаем всех рекрутеров
    recruiters = await admin_repository.get_all_recruiters()
    
    # Получаем количество заявок на регистрацию
    pending_requests = await registration_repository.get_pending_requests()
    pending_count = len(pending_requests)
    
    # Получаем всех заказчиков для выпадающего списка
    from app.database.database import CustomerDropdown
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.database.database import engine
    
    async with AsyncSession(engine) as session:
        result = await session.execute(select(CustomerDropdown))
        customers_raw = list(result.scalars().all())
        # Преобразуем SQLModel объекты в словари для шаблона
        all_customers = [{"id": c.id, "customer_name": c.customer_name} for c in customers_raw]
    
    return templates.TemplateResponse(
        "admin/dashboard.html",
        {
            "request": request,
            "admin_id": current_admin["id"],
            "recruiters": recruiters,
            "pending_registrations_count": pending_count,
            "all_customers": all_customers
        }
    )


@router.post("/create-recruiter")
async def create_recruiter(
    email: str = Form(...),
    current_admin=Depends(get_current_admin_from_cookie)
):
    """
    Создать новый аккаунт рекрутера.
    
    Генерирует случайный пароль и создает пользователя в системе.
    
    Args:
        email: Email рекрутера
        current_admin: Текущий администратор (из cookie)
        
    Returns:
        JSONResponse: JSON с данными созданного пользователя (email, password, user_id)
        
    Raises:
        HTTPException: Если не авторизован или пользователь уже существует
    """
    if not current_admin:
        raise HTTPException(status_code=401, detail="Не авторизован")
    
    # Генерируем пароль
    password = generate_password()
    
    # Создаем рекрутера
    user = await admin_repository.create_recruiter(
        email=email,
        password=password,
        admin_id=current_admin["id"]
    )
    
    if not user:
        raise HTTPException(status_code=400, detail="Пользователь с таким email уже существует")
    
    return JSONResponse(content={
        "success": True,
        "email": email,
        "password": password,
        "user_id": user.id
    })


@router.get("/logout")
async def admin_logout():
    """
    Выход администратора из системы.
    
    Удаляет cookie с токеном доступа и перенаправляет на страницу входа.
    
    Returns:
        RedirectResponse: Редирект на страницу логина администратора
    """
    response = RedirectResponse("/admin/login", status_code=303)
    response.delete_cookie("admin_access_token", path="/")
    return response


@router.post("/setup-initial-admin")
async def setup_initial_admin():
    """
    Создать первого администратора (только для первого запуска)
    Этот endpoint можно вызвать только если админов еще нет
    """
    # Проверяем есть ли уже админы
    from app.database.database import Admin, engine
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession
    
    async with AsyncSession(engine) as session:
        result = await session.execute(select(Admin))
        existing_admins = result.scalars().all()
        
        if existing_admins:
            raise HTTPException(status_code=400, detail="Администратор уже существует")
    
    # Создаем первого админа
    username = "admin"
    password = "OmegaAdmin2025!"
    
    admin = await admin_repository.create_admin(username, password)
    
    if not admin:
        raise HTTPException(status_code=500, detail="Не удалось создать администратора")
    
    # Сохраняем учетные данные в файл
    from pathlib import Path
    credentials_file = Path("admin_credentials.txt")
    with open(credentials_file, "w", encoding="utf-8") as f:
        f.write("=" * 60 + "\n")
        f.write("УЧЕТНЫЕ ДАННЫЕ АДМИНИСТРАТОРА\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"Логин:  {username}\n")
        f.write(f"Пароль: {password}\n")
        f.write(f"ID:     {admin.id}\n")
        f.write(f"\nURL для входа: http://localhost:8000/admin/login\n")
        f.write(f"               http://omegahire.tech/admin/login\n")
        f.write("\n⚠️ ВАЖНО: Храните этот файл в безопасном месте!\n")
    
    return JSONResponse(content={
        "success": True,
        "message": "Администратор создан",
        "username": username,
        "password": password,
        "admin_id": admin.id,
        "credentials_file": str(credentials_file.absolute())
    })


@router.get("/pending-registrations", response_class=HTMLResponse)
async def pending_registrations_page(
    request: Request,
    current_admin=Depends(get_current_admin_from_cookie)
):
    """
    Страница со списком заявок на регистрацию, ожидающих одобрения.
    
    Показывает все заявки с подтвержденным email, которые еще не обработаны.
    
    Args:
        request: FastAPI Request объект
        current_admin: Текущий администратор (из cookie)
        
    Returns:
        HTMLResponse: HTML страница с заявками или редирект на логин
    """
    if not current_admin:
        return RedirectResponse("/admin/login", status_code=303)
    
    pending_requests = await registration_repository.get_pending_requests()
    
    return templates.TemplateResponse(
        "admin/pending_registrations.html",
        {
            "request": request,
            "admin_id": current_admin["id"],
            "requests": pending_requests
        }
    )


@router.post("/approve-registration/{request_id}")
async def approve_registration(
    request_id: int,
    current_admin=Depends(get_current_admin_from_cookie)
):
    """
    Одобрить заявку на регистрацию и создать пользователя.
    
    Создает пользователя в системе и отправляет письмо с учетными данными.
    
    Args:
        request_id: ID заявки на регистрацию
        current_admin: Текущий администратор (из cookie)
        
    Returns:
        JSONResponse: JSON с результатом операции
        
    Raises:
        HTTPException: Если не авторизован, заявка не найдена или не удалось одобрить
    """
    if not current_admin:
        raise HTTPException(status_code=401, detail="Не авторизован")
    
    # Получаем заявку
    request_obj = await registration_repository.get_by_id(request_id)
    if not request_obj:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    
    # Одобряем и создаем пользователя
    user = await registration_repository.approve_request(request_id, current_admin["id"])
    if not user:
        raise HTTPException(status_code=400, detail="Не удалось одобрить заявку")
    
    # Отправляем письмо пользователю
    email_body = f"""
    <html>
    <body>
        <h2>Ваша заявка одобрена!</h2>
        <p>Здравствуйте!</p>
        <p>Ваша заявка на регистрацию в системе OmegaHire была одобрена администратором.</p>
        <p><strong>Ваши данные для входа:</strong></p>
        <p>Email: {user.email}</p>
        <p>Пароль: {user.password}</p>
        <p>Войти в систему: <a href="http://omegahire.tech/auth/login">http://omegahire.tech/auth/login</a></p>
        <br>
        <p>С уважением,<br>Команда OmegaHire</p>
    </body>
    </html>
    """
    
    try:
        await send_email_smtp(
            sender_email=settings.smtp_from_email,
            recipient_email=user.email,
            subject="Ваша заявка на OmegaHire одобрена",
            body=email_body,
            html=True,
            smtp_host=settings.smtp_host,
            smtp_port=settings.smtp_port,
            smtp_username=settings.smtp_username,
            smtp_password=settings.smtp_password,
            use_tls=settings.smtp_use_tls,
            use_starttls=settings.smtp_use_starttls,
        )
    except Exception as e:
        print(f"[ADMIN] ❌ Ошибка отправки письма: {e}")
    
    return JSONResponse(content={"success": True, "message": "Заявка одобрена"})


@router.post("/reject-registration/{request_id}")
async def reject_registration(
    request_id: int,
    current_admin=Depends(get_current_admin_from_cookie)
):
    """
    Отклонить заявку на регистрацию.
    
    Отмечает заявку как отклоненную и отправляет письмо пользователю.
    
    Args:
        request_id: ID заявки на регистрацию
        current_admin: Текущий администратор (из cookie)
        
    Returns:
        JSONResponse: JSON с результатом операции
        
    Raises:
        HTTPException: Если не авторизован, заявка не найдена или не удалось отклонить
    """
    if not current_admin:
        raise HTTPException(status_code=401, detail="Не авторизован")
    
    # Получаем заявку
    request_obj = await registration_repository.get_by_id(request_id)
    if not request_obj:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    
    # Отклоняем
    success = await registration_repository.reject_request(request_id, current_admin["id"])
    if not success:
        raise HTTPException(status_code=400, detail="Не удалось отклонить заявку")
    
    # Отправляем письмо пользователю
    email_body = f"""
    <html>
    <body>
        <h2>Ваша заявка отклонена</h2>
        <p>Здравствуйте!</p>
        <p>К сожалению, ваша заявка на регистрацию в системе OmegaHire была отклонена администратором.</p>
        <p>Если у вас есть вопросы, пожалуйста, свяжитесь с нами по адресу: {settings.smtp_from_email}</p>
        <br>
        <p>С уважением,<br>Команда OmegaHire</p>
    </body>
    </html>
    """
    
    try:
        await send_email_smtp(
            sender_email=settings.smtp_from_email,
            recipient_email=request_obj.email,
            subject="Ваша заявка на OmegaHire отклонена",
            body=email_body,
            html=True,
            smtp_host=settings.smtp_host,
            smtp_port=settings.smtp_port,
            smtp_username=settings.smtp_username,
            smtp_password=settings.smtp_password,
            use_tls=settings.smtp_use_tls,
            use_starttls=settings.smtp_use_starttls,
        )
    except Exception as e:
        print(f"[ADMIN] ❌ Ошибка отправки письма: {e}")
    
    return JSONResponse(content={"success": True, "message": "Заявка отклонена"})


@router.get("/candidates", response_class=HTMLResponse)
async def view_all_candidates(
    request: Request,
    current_admin=Depends(get_current_admin_from_cookie)
):
    """
    Просмотр всех кандидатов из всех рекрутеров.
    
    Администратор может видеть всех кандидатов независимо от рекрутера.
    
    Args:
        request: FastAPI Request объект
        current_admin: Текущий администратор (из cookie)
        
    Returns:
        HTMLResponse: HTML страница со списком всех кандидатов или редирект на логин
    """
    if not current_admin:
        return RedirectResponse("/admin/login", status_code=303)
    
    candidates = await admin_repository.get_all_candidates()
    
    return templates.TemplateResponse(
        "admin/candidates.html",
        {
            "request": request,
            "admin_id": current_admin["id"],
            "candidates": candidates
        }
    )


@router.get("/sverkas", response_class=HTMLResponse)
async def view_all_sverkas(
    request: Request,
    current_admin=Depends(get_current_admin_from_cookie)
):
    """
    Просмотр всех сверок из всех рекрутеров.
    
    Администратор может видеть все сверки независимо от рекрутера.
    
    Args:
        request: FastAPI Request объект
        current_admin: Текущий администратор (из cookie)
        
    Returns:
        HTMLResponse: HTML страница со списком всех сверок или редирект на логин
    """
    if not current_admin:
        return RedirectResponse("/admin/login", status_code=303)
    
    sverkas = await admin_repository.get_all_sverkas()
    
    # Получаем данные пользователей для ссылок
    from app.database.database import User
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.database.database import engine
    from app.core.utils import norm_tg
    
    # Создаем словарь user_id -> user для быстрого доступа
    user_ids = {s.user_id for s in sverkas if s.user_id}
    users_dict = {}
    
    if user_ids:
        async with AsyncSession(engine) as session:
            result = await session.execute(
                select(User).where(User.id.in_(user_ids))
            )
            users = result.scalars().all()
            for user in users:
                users_dict[user.id] = {
                    "email": user.email,
                    "work_telegram": norm_tg(user.work_telegram or "") if user.work_telegram else ""
                }
    
    return templates.TemplateResponse(
        "admin/sverkas.html",
        {
            "request": request,
            "admin_id": current_admin["id"],
            "sverkas": sverkas,
            "users_dict": users_dict  # Передаем словарь пользователей
        }
    )


@router.post("/grant-customer-access")
async def grant_customer_access(
    user_id: int = Form(...),
    customer_id: int = Form(...),
    current_admin=Depends(get_current_admin_from_cookie)
):
    """
    Предоставить рекрутеру доступ к заказчику.
    
    Args:
        user_id: ID рекрутера
        customer_id: ID заказчика
        current_admin: Текущий администратор (из cookie)
        
    Returns:
        JSONResponse: JSON с результатом операции
    """
    if not current_admin:
        raise HTTPException(status_code=401, detail="Не авторизован")
    
    success = await admin_repository.grant_customer_access(user_id, customer_id)
    if not success:
        raise HTTPException(status_code=400, detail="Доступ уже предоставлен или произошла ошибка")
    
    return JSONResponse(content={"success": True, "message": "Доступ предоставлен"})


@router.post("/revoke-customer-access")
async def revoke_customer_access(
    user_id: int = Form(...),
    customer_id: int = Form(...),
    current_admin=Depends(get_current_admin_from_cookie)
):
    """
    Отозвать доступ рекрутера к заказчику.
    
    Args:
        user_id: ID рекрутера
        customer_id: ID заказчика
        current_admin: Текущий администратор (из cookie)
        
    Returns:
        JSONResponse: JSON с результатом операции
    """
    if not current_admin:
        raise HTTPException(status_code=401, detail="Не авторизован")
    
    success = await admin_repository.revoke_customer_access(user_id, customer_id)
    if not success:
        raise HTTPException(status_code=404, detail="Доступ не найден")
    
    return JSONResponse(content={"success": True, "message": "Доступ отозван"})


@router.post("/change-user-password")
async def change_user_password(
    user_id: int = Form(...),
    new_password: str = Form(...),
    current_admin=Depends(get_current_admin_from_cookie)
):
    """
    Изменить пароль пользователя администратором.
    
    Args:
        user_id: ID рекрутера
        new_password: Новый пароль
        current_admin: Текущий администратор (из cookie)
        
    Returns:
        JSONResponse: JSON с результатом операции
    """
    if not current_admin:
        raise HTTPException(status_code=401, detail="Не авторизован")
    
    user = await admin_repository.change_user_password(user_id, new_password)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    # Отправляем письмо пользователю
    email_body = f"""
    <html>
    <body>
        <h2>Пароль изменен</h2>
        <p>Здравствуйте!</p>
        <p>Администратор изменил пароль для вашего аккаунта в системе OmegaHire.</p>
        <p><strong>Ваш новый пароль:</strong></p>
        <p style="font-size: 18px; font-weight: bold; background: #f1f5f9; padding: 10px; border-radius: 6px; display: inline-block;">{new_password}</p>
        <p>Войти в систему: <a href="http://omegahire.tech/auth/login">http://omegahire.tech/auth/login</a></p>
        <br>
        <p>С уважением,<br>Команда OmegaHire</p>
    </body>
    </html>
    """
    
    try:
        await send_email_smtp(
            sender_email=settings.smtp_from_email,
            recipient_email=user.email,
            subject="Изменение пароля OmegaHire",
            body=email_body,
            html=True,
            smtp_host=settings.smtp_host,
            smtp_port=settings.smtp_port,
            smtp_username=settings.smtp_username,
            smtp_password=settings.smtp_password,
            use_tls=settings.smtp_use_tls,
            use_starttls=settings.smtp_use_starttls,
        )
    except Exception as e:
        print(f"[ADMIN] ❌ Ошибка отправки письма: {e}")
        # Не возвращаем ошибку, так как пароль уже изменен
    
    return JSONResponse(content={"success": True, "message": "Пароль успешно изменен"})


@router.post("/archive-user")
async def archive_user(
    user_id: int = Form(...),
    current_admin=Depends(get_current_admin_from_cookie)
):
    """
    Перевести пользователя в архив.
    
    Пользователи в архиве не могут входить в систему.
    
    Args:
        user_id: ID рекрутера
        current_admin: Текущий администратор (из cookie)
        
    Returns:
        JSONResponse: JSON с результатом операции
    """
    if not current_admin:
        raise HTTPException(status_code=401, detail="Не авторизован")
    
    from app.database.user_db import UserRepository
    user_repo = UserRepository()
    
    user = await user_repo.archive_user(user_id, current_admin["id"])
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    # Отправляем письмо пользователю
    email_body = f"""
    <html>
    <body>
        <h2>Аккаунт переведен в архив</h2>
        <p>Здравствуйте!</p>
        <p>Ваш аккаунт в системе OmegaHire был переведен в архив администратором и <strong>заблокирован</strong>.</p>
        <p>Вы больше не можете войти в систему. Если вы были авторизованы, система автоматически завершит вашу текущую сессию.</p>
        <p>Если у вас есть вопросы, пожалуйста, свяжитесь с администратором: {settings.smtp_from_email}</p>
        <br>
        <p>С уважением,<br>Команда OmegaHire</p>
    </body>
    </html>
    """
    
    try:
        await send_email_smtp(
            sender_email=settings.smtp_from_email,
            recipient_email=user.email,
            subject="Аккаунт переведен в архив - OmegaHire",
            body=email_body,
            html=True,
            smtp_host=settings.smtp_host,
            smtp_port=settings.smtp_port,
            smtp_username=settings.smtp_username,
            smtp_password=settings.smtp_password,
            use_tls=settings.smtp_use_tls,
            use_starttls=settings.smtp_use_starttls,
        )
    except Exception as e:
        print(f"[ADMIN] ❌ Ошибка отправки письма: {e}")
    
    return JSONResponse(content={"success": True, "message": "Пользователь переведен в архив"})


@router.post("/unarchive-user")
async def unarchive_user(
    user_id: int = Form(...),
    current_admin=Depends(get_current_admin_from_cookie)
):
    """
    Восстановить пользователя из архива.
    
    Args:
        user_id: ID рекрутера
        current_admin: Текущий администратор (из cookie)
        
    Returns:
        JSONResponse: JSON с результатом операции
    """
    if not current_admin:
        raise HTTPException(status_code=401, detail="Не авторизован")
    
    from app.database.user_db import UserRepository
    user_repo = UserRepository()
    
    user = await user_repo.unarchive_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    # Отправляем письмо пользователю
    email_body = f"""
    <html>
    <body>
        <h2>Аккаунт восстановлен из архива</h2>
        <p>Здравствуйте!</p>
        <p>Ваш аккаунт в системе OmegaHire был восстановлен из архива и <strong>разблокирован</strong>.</p>
        <p>Теперь вы снова можете войти в систему, используя свои учетные данные.</p>
        <p>Войти в систему: <a href="http://omegahire.tech/auth/login">http://omegahire.tech/auth/login</a></p>
        <br>
        <p>С уважением,<br>Команда OmegaHire</p>
    </body>
    </html>
    """
    
    try:
        await send_email_smtp(
            sender_email=settings.smtp_from_email,
            recipient_email=user.email,
            subject="Аккаунт восстановлен - OmegaHire",
            body=email_body,
            html=True,
            smtp_host=settings.smtp_host,
            smtp_port=settings.smtp_port,
            smtp_username=settings.smtp_username,
            smtp_password=settings.smtp_password,
            use_tls=settings.smtp_use_tls,
            use_starttls=settings.smtp_use_starttls,
        )
    except Exception as e:
        print(f"[ADMIN] ❌ Ошибка отправки письма: {e}")
    
    return JSONResponse(content={"success": True, "message": "Пользователь восстановлен из архива"})


@router.get("/user-customer-access/{user_id}")
async def get_user_customer_access(
    user_id: int,
    current_admin=Depends(get_current_admin_from_cookie)
):
    """
    Получить список заказчиков, к которым у рекрутера есть доступ.
    
    Args:
        user_id: ID рекрутера
        current_admin: Текущий администратор (из cookie)
        
    Returns:
        JSONResponse: JSON со списком ID заказчиков
    """
    if not current_admin:
        raise HTTPException(status_code=401, detail="Не авторизован")
    
    customer_ids = await admin_repository.get_user_customer_access(user_id)
    return JSONResponse(content={"customer_ids": customer_ids})


@router.get("/check-customer-access")
async def check_customer_access(
    current_user=Depends(get_current_user_from_cookie)
):
    """
    Проверить есть ли у текущего пользователя доступ к заказчикам.
    Используется фронтендом для определения показывать ли фильтр заказчиков.
    
    Args:
        current_user: Текущий пользователь (из cookie)
        
    Returns:
        JSONResponse: JSON с информацией о доступе
    """
    if not current_user:
        return JSONResponse(content={"has_access": False})
    
    has_access = await admin_repository.has_customer_access(current_user.id)
    return JSONResponse(content={"has_access": has_access})


# ============================================
# ПРОСМОТР ИСТОРИИ СВЕРОК ПОЛЬЗОВАТЕЛЯ
# ============================================

@router.get("/user/{user_id}/candidates", response_class=HTMLResponse)
async def admin_user_candidates(
    user_id: int,
    request: Request,
    current_admin=Depends(get_current_admin_from_cookie)
):
    """
    Просмотр всех кандидатов рекрутера с их сверками (для администратора).
    При клике на кандидата показываются все его сверки.
    
    Args:
        user_id: ID пользователя (рекрутера)
        request: FastAPI Request объект
        current_admin: Текущий администратор (из cookie)
        
    Returns:
        HTMLResponse: HTML страница с кандидатами и их сверками или редирект на логин
    """
    if not current_admin:
        return RedirectResponse("/admin/login", status_code=303)
    
    # Проверяем существование пользователя
    from app.database.database import User
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.database.database import engine
    
    async with AsyncSession(engine) as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalars().first()
        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    # Получаем всех кандидатов рекрутера
    from app.database.candidate_db import CandidateRepository
    candidate_repo = CandidateRepository()
    candidates = await candidate_repo.get_all_candidates_for_user(user_id)
    
    # Получаем все сверки рекрутера
    from app.database.database import Sverka
    
    async with AsyncSession(engine) as session:
        result = await session.execute(
            select(Sverka).where(Sverka.user_id == user_id)
        )
        all_sverkas = list(result.scalars().all())
    
    # Группируем сверки по кандидатам (по candidate_fullname)
    # Для каждого кандидата формируем полное имя и ищем его сверки
    candidates_with_sverkas = []
    for candidate in candidates:
        # Формируем полное имя кандидата в разных вариантах для сопоставления
        name_parts = []
        if candidate.first_name:
            name_parts.append(candidate.first_name)
        if candidate.last_name:
            name_parts.append(candidate.last_name)
        if candidate.middle_name:
            name_parts.append(candidate.middle_name)
        full_name = " ".join(name_parts) if name_parts else None
        
        # Варианты имени для сопоставления (убираем лишние пробелы, приводим к нижнему регистру)
        name_variants = set()
        if full_name:
            name_variants.add(full_name.strip().lower())
            # Вариант без отчества
            if candidate.first_name and candidate.last_name:
                name_variants.add(f"{candidate.first_name} {candidate.last_name}".strip().lower())
            # Вариант только фамилия и имя в обратном порядке
            if candidate.last_name and candidate.first_name:
                name_variants.add(f"{candidate.last_name} {candidate.first_name}".strip().lower())
        
        # Ищем сверки по полному имени (гибкое сопоставление)
        candidate_sverkas = []
        if name_variants:
            for sverka in all_sverkas:
                if sverka.candidate_fullname:
                    sverka_name = sverka.candidate_fullname.strip().lower()
                    # Проверяем точное совпадение или вхождение имени
                    if sverka_name in name_variants or any(variant in sverka_name or sverka_name in variant for variant in name_variants):
                        candidate_sverkas.append(sverka)
        
        candidates_with_sverkas.append({
            "candidate": candidate,
            "full_name": full_name or "Без имени",
            "sverkas": candidate_sverkas
        })
    
    from app.core.utils import norm_tg
    tg_username = norm_tg(user.work_telegram or "")
    
    return templates.TemplateResponse(
        "admin/user_candidates.html",
        {
            "request": request,
            "user_id": user_id,
            "user_email": user.email,
            "telegram_username": tg_username,
            "candidates_with_sverkas": candidates_with_sverkas,
            "admin_id": current_admin["id"],
        },
    )


@router.get("/user/{user_id}/sverka-history", response_class=HTMLResponse)
async def admin_user_sverka_history(
    user_id: int,
    request: Request,
    current_admin=Depends(get_current_admin_from_cookie)
):
    """
    Просмотр истории сверок конкретного пользователя администратором.
    
    Args:
        user_id: ID пользователя (рекрутера)
        request: FastAPI Request объект
        current_admin: Текущий администратор (из cookie)
        
    Returns:
        HTMLResponse: HTML страница с историей сверок или редирект на логин
    """
    if not current_admin:
        return RedirectResponse("/admin/login", status_code=303)
    
    # Проверяем существование пользователя
    from app.database.database import User
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.database.database import engine
    
    async with AsyncSession(engine) as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalars().first()
        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    # Получаем историю сверок пользователя
    from app.database.user_db import UserRepository
    user_repo = UserRepository()
    history = await user_repo.get_sverka_history(user_id)
    
    return templates.TemplateResponse(
        "sverka/sverka_history.html",
        {
            "request": request,
            "items": history,
            "user_email": user.email,
            "user_id": user_id,
            "telegram_username": user.work_telegram,
            "is_admin_view": True,  # Флаг для шаблона
            "admin_id": current_admin["id"],
        },
    )


@router.get("/user/{user_id}/sverka-history/detail", response_class=HTMLResponse)
async def admin_user_sverka_history_detail(
    user_id: int,
    request: Request,
    vacancy_id: str = Query(...),
    current_admin=Depends(get_current_admin_from_cookie),
):
    """
    Детальный просмотр сверок пользователя по конкретной вакансии (для администратора).
    
    Args:
        user_id: ID пользователя (рекрутера)
        request: FastAPI Request объект
        vacancy_id: ID вакансии
        current_admin: Текущий администратор (из cookie)
        
    Returns:
        HTMLResponse: HTML страница с деталями сверок или редирект на логин
    """
    if not current_admin:
        return RedirectResponse("/admin/login", status_code=303)
    
    # Проверяем существование пользователя
    from app.database.database import User
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.database.database import engine
    
    async with AsyncSession(engine) as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalars().first()
        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    # Получаем сверки по вакансии
    from app.database.vacancy_db import VacancyRepository
    vacancy_repo = VacancyRepository()
    rows = await vacancy_repo.get_sverka_history_by_user_and_vacancy(
        user_id=user_id,
        vacancy_id=vacancy_id,
    )
    
    # Приводим к формату для шаблона
    results: list[dict] = []
    for row in rows:
        results.append(
            {
                "resume_json": row.sverka_json,
                "filename": row.candidate_fullname or f"candidate_{row.id}",
                "candidate_fullname": row.candidate_fullname,
                'slug': row.slug,
            }
        )
    
    from app.core.utils import norm_tg
    tg_username = norm_tg(user.work_telegram or "")
    task_id = f"history-{vacancy_id}"
    
    return templates.TemplateResponse(
        "sverka/sverka_history_result.html",
        {
            "request": request,
            "task_id": task_id,
            "vacancy_id": vacancy_id,
            "results": results,
            "tg_username": tg_username,
            "user_email": user.email,
            "user_id": user_id,
            "is_admin_view": True,  # Флаг для шаблона
            "admin_id": current_admin["id"],
        },
    )


@router.get("/user/{user_id}/sverka-history/result-{vacancy_id}/{slug}", response_class=HTMLResponse)
async def admin_user_sverka_result_history_one(
    user_id: int,
    request: Request,
    vacancy_id: str,
    slug: str,
    tg_username: Annotated[str, Query(...)],
    current_admin=Depends(get_current_admin_from_cookie),
):
    """
    Просмотр конкретной сверки из истории пользователя (для администратора).
    
    Args:
        user_id: ID пользователя (рекрутера)
        request: FastAPI Request объект
        vacancy_id: ID вакансии
        slug: Slug сверки
        tg_username: Telegram username
        current_admin: Текущий администратор (из cookie)
        
    Returns:
        HTMLResponse: HTML страница с результатом сверки или редирект на логин
    """
    if not current_admin:
        return RedirectResponse("/admin/login", status_code=303)
    
    # Проверяем существование пользователя
    from app.database.database import User
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.database.database import engine
    
    async with AsyncSession(engine) as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalars().first()
        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    # Получаем сверку
    from app.database.user_db import UserRepository
    user_repo = UserRepository()
    sverkas = await user_repo.get_sverka_by_vac_id_and_slug(
        vacancy_id=vacancy_id,
        user_id=user_id,
        slug=slug,
    )
    
    if not sverkas:
        raise HTTPException(status_code=404, detail="Сверка не найдена")
    
    # Формируем данные для шаблона
    from app.core.utils import display_analysis
    resume_json = sverkas.sverka_json or {}
    candidate_fullname = sverkas.candidate_fullname or "Кандидат"
    ai_text = display_analysis(resume_json)
    contacts = resume_json.get("candidate", {}).get("contacts", {})
    
    return templates.TemplateResponse(
        "sverka/sverka_result.html",
        {
            "request": request,
            "task_id": f"history-{vacancy_id}",
            "ai_text": ai_text,
            "vacancy_id": vacancy_id,
            "candidate_fullname": candidate_fullname,
            "contacts": contacts,
            "tg_username": tg_username,
            "user_email": user.email,
            "user_id": user_id,
            "is_admin_view": True,  # Флаг для шаблона
            "admin_id": current_admin["id"],
        },
    )


@router.get("/candidate/open/{user_id}/{candidate_id}", response_class=HTMLResponse)
async def admin_open_candidate(
    user_id: int,
    candidate_id: int,
    request: Request,
    current_admin=Depends(get_current_admin_from_cookie),
):
    """
    Просмотр карточки кандидата конкретного пользователя (для администратора).
    
    Args:
        user_id: ID пользователя (рекрутера)
        candidate_id: ID кандидата (number_for_user)
        request: FastAPI Request объект
        current_admin: Текущий администратор (из cookie)
        
    Returns:
        HTMLResponse: HTML страница с карточкой кандидата или редирект на логин
    """
    if not current_admin:
        return RedirectResponse("/admin/login", status_code=303)
    
    # Получаем кандидата по user_id и candidate_id
    from app.database.candidate_db import CandidateRepository
    candidate_repo = CandidateRepository()
    
    candidate = await candidate_repo.get_candidate_by_id_and_user_id(
        number_for_user=candidate_id,
        user_id=user_id
    )
    
    if not candidate:
        raise HTTPException(status_code=404, detail="Кандидат не найден")
    
    # Получаем данные пользователя для отображения
    from app.database.database import User
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.database.database import engine
    
    async with AsyncSession(engine) as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalars().first()
        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    return templates.TemplateResponse(
        "candidate/candidate_open.html",
        {
            "request": request,
            "candidate": candidate,
            "candidate_id": candidate_id,
            "user_email": user.email,
            "user_id": user_id,
            "is_admin_view": True,  # Флаг для шаблона
            "admin_id": current_admin["id"],
        },
    )


# ============================================
# ПРОСМОТР ЧАТОВ И ДИАЛОГОВ ПОЛЬЗОВАТЕЛЕЙ
# ============================================

@router.get("/chats", response_class=HTMLResponse)
async def admin_chats(
    request: Request,
    current_admin=Depends(get_current_admin_from_cookie),
):
    """
    Просмотр всех пользователей с чатами (для администратора).
    
    Args:
        request: FastAPI Request объект
        current_admin: Текущий администратор (из cookie)
        
    Returns:
        HTMLResponse: HTML страница со списком пользователей с чатами или редирект на логин
    """
    if not current_admin:
        return RedirectResponse("/admin/login", status_code=303)
    
    # Получаем всех пользователей с чатами
    users_with_chats = await chat_repository.get_all_users_with_chats()
    
    return templates.TemplateResponse(
        "admin/chats.html",
        {
            "request": request,
            "admin_id": current_admin["id"],
            "users_with_chats": users_with_chats,
        },
    )


@router.get("/user/{user_id}/chats", response_class=HTMLResponse)
async def admin_user_chats(
    user_id: int,
    request: Request,
    current_admin=Depends(get_current_admin_from_cookie),
):
    """
    Просмотр всех диалогов конкретного пользователя (для администратора).
    
    Args:
        user_id: ID пользователя (рекрутера)
        request: FastAPI Request объект
        current_admin: Текущий администратор (из cookie)
        
    Returns:
        HTMLResponse: HTML страница с диалогами пользователя или редирект на логин
    """
    if not current_admin:
        return RedirectResponse("/admin/login", status_code=303)
    
    # Проверяем существование пользователя
    from app.database.database import User
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.database.database import engine
    
    async with AsyncSession(engine) as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalars().first()
        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    # Получаем все чаты пользователя
    chats = await chat_repository.get_user_chats(user_id)
    
    # Разделяем на Telegram и Email
    telegram_chats = [c for c in chats if c["message_type"] == "telegram"]
    email_chats = [c for c in chats if c["message_type"] == "email"]
    
    return templates.TemplateResponse(
        "admin/user_chats.html",
        {
            "request": request,
            "admin_id": current_admin["id"],
            "user_id": user_id,
            "user_email": user.email,
            "telegram_chats": telegram_chats,
            "email_chats": email_chats,
        },
    )


@router.get("/user/{user_id}/chat/{message_type}/{candidate_fullname}", response_class=HTMLResponse)
async def admin_chat_messages(
    user_id: int,
    message_type: str,
    candidate_fullname: str,
    request: Request,
    current_admin=Depends(get_current_admin_from_cookie),
):
    """
    Просмотр всех сообщений конкретного диалога (для администратора).
    
    Args:
        user_id: ID пользователя (рекрутера)
        message_type: Тип сообщения ('telegram' или 'email')
        candidate_fullname: Полное имя кандидата
        request: FastAPI Request объект
        current_admin: Текущий администратор (из cookie)
        
    Returns:
        HTMLResponse: HTML страница с сообщениями диалога или редирект на логин
    """
    if not current_admin:
        return RedirectResponse("/admin/login", status_code=303)
    
    # Проверяем существование пользователя
    from app.database.database import User
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.database.database import engine
    
    async with AsyncSession(engine) as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalars().first()
        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    # Получаем все сообщения диалога
    messages = await chat_repository.get_chat_messages_admin(
        user_id=user_id,
        candidate_fullname=candidate_fullname,
        message_type=message_type,
        limit=1000,
    )
    
    # Преобразуем в список словарей для шаблона
    messages_data = [
        {
            "id": msg.id,
            "sender": msg.sender,
            "message_text": msg.message_text,
            "timestamp": msg.timestamp,
            "is_read": msg.is_read,
            "vacancy_id": msg.vacancy_id,
            "vacancy_title": msg.vacancy_title,
            "has_media": msg.has_media,
            "media_type": msg.media_type,
            "media_path": msg.media_path,
            "media_filename": msg.media_filename,
        }
        for msg in messages
    ]
    
    vacancy_id = messages[0].vacancy_id if messages else None
    vacancy_title = messages[0].vacancy_title if messages else None
    
    return templates.TemplateResponse(
        "admin/chat_messages.html",
        {
            "request": request,
            "admin_id": current_admin["id"],
            "user_id": user_id,
            "user_email": user.email,
            "candidate_fullname": candidate_fullname,
            "message_type": message_type,
            "messages": messages_data,
            "vacancy_id": vacancy_id,
            "vacancy_title": vacancy_title,
        },
    )