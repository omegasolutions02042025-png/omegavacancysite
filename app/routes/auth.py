from click.types import UUID
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, Response, FileResponse
from starlette.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi.templating import Jinja2Templates
import os

from app.core.security import auth as authx
from app.core.current_user import get_current_user_from_cookie
from app.models.user import UserCreate
from fastapi import HTTPException
from app.database.user_db import UserRepository
from app.database.registration_db import registration_repository
from app.database.database import UserRole
from pathlib import Path
from app.core.email_send import send_email_smtp
from app.core.config import settings

router = APIRouter(prefix="/auth", tags=["Аутентификация"])
user_repo = UserRepository()
templates_dir = str(Path(__file__).resolve().parent.parent / "templates")
templates = Jinja2Templates(directory=templates_dir)


# Регистрация отключена - аккаунты создаются только администратором
# @router.post("/register")
# async def register(user: UserCreate):
#     email = user.email
#     password = user.password
#     print(email, password)
#     status = await user_repo.create_user(email=email, password=password)
#     if not status:
#         print("User already exists")
#         return HTTPException(status_code=400, detail="User already exists")

#     token = authx.create_access_token(uid=str(status.id))

#     response = RedirectResponse("/auth/profile", status_code=303)
#     response.set_cookie(
#         "access_token",
#         token,
#         httponly=True,
#         samesite="lax",
#         path="/"
#     )

#     return response



@router.post("/login")
async def login(email: str = Form(...), password: str = Form(...)):
    """
    Аутентификация пользователя по email и паролю.
    
    Args:
        email: Email пользователя
        password: Пароль пользователя
        
    Returns:
        RedirectResponse: Редирект на страницу профиля с установленной cookie access_token
        
    Raises:
        HTTPException: Если учетные данные неверны или пользователь в архиве
    """
    user = await user_repo.authenticate(email, password)
    if not user:
        raise HTTPException(status_code=400, detail="Неверный email или пароль")
    
    # Проверяем, не находится ли пользователь в архиве
    if user.is_archived:
        print(f"[AUTH] ❌ Попытка входа архивного пользователя: {email}")
        raise HTTPException(
            status_code=403, 
            detail="Ваш аккаунт заблокирован администратором. Обратитесь в поддержку для восстановления доступа."
        )
    
    token = authx.create_access_token(uid=str(user.id))
    print(token)
    response = RedirectResponse("/auth/profile", status_code=303)
    response.set_cookie(
        "access_token",
        token,
        httponly=True,
        samesite="lax",
        path="/"
    )
    return response

@router.get("/profile-data")
async def get_profile_data(
    current_user=Depends(get_current_user_from_cookie),
):
    """
    Получить данные профиля пользователя (включая photo_path и все поля профиля) для JS.
    Также возвращает данные профиля кандидата или подрядчика, если они есть.
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    from fastapi.responses import JSONResponse
    from app.database.database import UserRole
    from app.database.candidate_profile_db import CandidateProfileRepository
    from app.models.users import ContractorProfile
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.database.database import engine
    
    response_data = {
        "photo_path": current_user.photo_path if current_user.photo_path else None,
        "email": current_user.email,
        "first_name": current_user.first_name,
        "last_name": current_user.last_name,
        "middle_name": current_user.middle_name,
        "phone": current_user.phone,
        "specialization": current_user.specialization,
        "experience": current_user.experience,
        "resume": current_user.resume,
    }
    
    # Загружаем профиль кандидата, если роль CANDIDATE
    if current_user.role == UserRole.CANDIDATE:
        candidate_profile_repo = CandidateProfileRepository()
        candidate_profile = await candidate_profile_repo.get_by_user_id(current_user.id)
        if candidate_profile:
            response_data["candidate_profile"] = {
                "grade": candidate_profile.grade.value if candidate_profile.grade else None,
                "experience_years": candidate_profile.experience_years,
                "stack": candidate_profile.stack if candidate_profile.stack else [],
                "resume_url": candidate_profile.resume_url,
                "bio": candidate_profile.bio,
            }
        else:
            response_data["candidate_profile"] = None
    
    # Загружаем профиль подрядчика, если роль CONTRACTOR
    elif current_user.role == UserRole.CONTRACTOR:
        async with AsyncSession(engine) as session:
            result = await session.execute(
                select(ContractorProfile).where(ContractorProfile.user_id == current_user.id)
            )
            contractor_profile = result.scalar_one_or_none()
            if contractor_profile:
                response_data["contractor_profile"] = {
                    "grade": contractor_profile.grade.value if contractor_profile.grade else None,
                    "experience_years": contractor_profile.experience_years,
                    "stack": contractor_profile.stack if contractor_profile.stack else [],
                    "hourly_rate_usd": contractor_profile.hourly_rate_usd,
                    "is_available": contractor_profile.is_available,
                    "portfolio_url": contractor_profile.portfolio_url,
                    "bio": contractor_profile.bio,
                }
            else:
                response_data["contractor_profile"] = None
    
    return JSONResponse(content=response_data)


@router.get("/profile", response_class=HTMLResponse)
async def profile(
    request: Request,
    current_user=Depends(get_current_user_from_cookie),
):
    """
    Страница профиля пользователя.
    
    Выбирает шаблон в зависимости от роли пользователя:
    - CANDIDATE -> profile_candidate.html
    - CONTRACTOR -> profile_contractor.html
    - RECRUITER/ADMIN -> profile.html (стандартный)
    
    Args:
        request: FastAPI Request объект
        current_user: Текущий авторизованный пользователь (из cookie)
        
    Returns:
        HTMLResponse: HTML страница профиля или редирект на логин если не авторизован
    """
    if not current_user:
        return RedirectResponse("/auth/login", status_code=303)
    
    from app.database.database import UserRole
    from app.database.candidate_profile_db import CandidateProfileRepository
    from app.models.users import ContractorProfile
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.database.database import engine
    
    user_role = current_user.role
    template_name = "auth/profile.html"
    template_context = {
        "request": request,
        "user_id": current_user.id,
        "user_email": current_user.email,
        "user_first_name": current_user.first_name,
        "user_last_name": current_user.last_name,
        "user_middle_name": current_user.middle_name,
        "user_phone": current_user.phone,
        "user_specialization": current_user.specialization,
        "user_experience": current_user.experience,
        "user_resume": current_user.resume,
        "telegram_username": current_user.work_telegram,
        "linked_email": current_user.work_email,
    }
    
    # Для кандидатов загружаем профиль кандидата
    if user_role == UserRole.CANDIDATE:
        template_name = "auth/profile_candidate.html"
        candidate_profile_repo = CandidateProfileRepository()
        candidate_profile = await candidate_profile_repo.get_by_user_id(current_user.id)
        if candidate_profile:
            template_context["candidate_profile"] = {
                "grade": candidate_profile.grade.value if candidate_profile.grade else None,
                "experience_years": candidate_profile.experience_years,
                "stack": candidate_profile.stack if candidate_profile.stack else [],
                "resume_url": candidate_profile.resume_url,
                "bio": candidate_profile.bio,
            }
        else:
            template_context["candidate_profile"] = None
    
    # Для подрядчиков загружаем профиль подрядчика
    elif user_role == UserRole.CONTRACTOR:
        template_name = "auth/profile_contractor.html"
        async with AsyncSession(engine) as session:
            result = await session.execute(
                select(ContractorProfile).where(ContractorProfile.user_id == current_user.id)
            )
            contractor_profile = result.scalar_one_or_none()
            if contractor_profile:
                template_context["contractor_profile"] = {
                    "grade": contractor_profile.grade.value if contractor_profile.grade else None,
                    "experience_years": contractor_profile.experience_years,
                    "stack": contractor_profile.stack if contractor_profile.stack else [],
                    "hourly_rate_usd": contractor_profile.hourly_rate_usd,
                    "is_available": contractor_profile.is_available,
                    "portfolio_url": contractor_profile.portfolio_url,
                    "bio": contractor_profile.bio,
                }
            else:
                template_context["contractor_profile"] = None
    
    return templates.TemplateResponse(template_name, template_context)



# Регистрация отключена - аккаунты создаются только администратором
# @router.get("/register")
# async def register_page(request: Request):
#   """Показать страницу регистрации"""
#   return templates.TemplateResponse("auth/register.html", {"request": request})


@router.get("/login")
async def login_page(request: Request):
  """Показать страницу логина"""
  return templates.TemplateResponse("auth/login.html", {"request": request})

@router.get("/logout")
async def logout():
    """
    Выход пользователя из системы.
    Удаляет cookie с токеном доступа и перенаправляет на страницу входа.
    
    Returns:
        RedirectResponse: Редирект на страницу логина
    """
    resp = RedirectResponse("/auth/login", status_code=303)
    # ВАЖНО: то же имя и path, что и при установке
    resp.delete_cookie("access_token", path="/")
    return resp

@router.get("/forgot-password")
async def forgot_password_page(request: Request):
    """
    Показать страницу восстановления пароля.
    
    Пользователь вводит email, на который будет отправлена ссылка для восстановления.
    """
    return templates.TemplateResponse("auth/forgot_password.html", {"request": request})

@router.post("/forgot-password")
async def forgot_password(
    email: str = Form(...),
):
    """
    Отправка ссылки для восстановления пароля на email.
    
    Проверяет, что пользователь существует и аккаунт подтвержден администратором.
    Генерирует токен и отправляет ссылку на email.
    
    Args:
        email: Email пользователя
        
    Returns:
        JSONResponse: Сообщение об успешной отправке
        
    Raises:
        HTTPException: Если пользователь не найден или аккаунт не подтвержден
    """
    # Проверяем, что пользователь существует
    user = await user_repo.get_by_email(email)
    if not user:
        raise HTTPException(
            status_code=404,
            detail="Пользователь с таким email не найден или аккаунт не подтвержден администратором"
        )
    
    # Проверяем, что аккаунт подтвержден (создан администратором)
    if not user.created_by_admin:
        raise HTTPException(
            status_code=404,
            detail="Аккаунт не подтвержден. Обратитесь к администратору."
        )
    
    # Создаем токен восстановления
    token = await user_repo.create_password_reset_token(email)
    if not token:
        raise HTTPException(
            status_code=500,
            detail="Не удалось создать токен восстановления"
        )
    
    # Отправляем письмо с ссылкой
    reset_link = f"http://omegahire.tech/auth/reset-password?token={token}"
    
    email_body = f"""
    <html>
    <body>
        <h2>Восстановление пароля на OmegaHire</h2>
        <p>Здравствуйте!</p>
        <p>Вы запросили восстановление пароля для вашего аккаунта.</p>
        <p>Для установки нового пароля перейдите по ссылке:</p>
        <p><a href="{reset_link}">{reset_link}</a></p>
        <p>Ссылка действительна в течение 24 часов.</p>
        <p>Если вы не запрашивали восстановление пароля, проигнорируйте это письмо.</p>
        <br>
        <p>С уважением,<br>Команда OmegaHire</p>
    </body>
    </html>
    """
    
    try:
        success = await send_email_smtp(
            sender_email=settings.smtp_from_email,
            recipient_email=email,
            subject="Восстановление пароля на OmegaHire",
            body=email_body,
            html=True,
            smtp_host=settings.smtp_host,
            smtp_port=settings.smtp_port,
            smtp_username=settings.smtp_username,
            smtp_password=settings.smtp_password,
            use_tls=settings.smtp_use_tls,
            use_starttls=settings.smtp_use_starttls,
        )
        
        if not success:
            print(f"[PASSWORD RESET] ⚠️ Не удалось отправить письмо на {email}")
            raise HTTPException(
                status_code=500,
                detail="Не удалось отправить письмо. Попробуйте позже."
            )
    except Exception as e:
        print(f"[PASSWORD RESET] ❌ Ошибка отправки письма: {e}")
        raise HTTPException(
            status_code=500,
            detail="Ошибка отправки письма. Попробуйте позже."
        )
    
    from fastapi.responses import JSONResponse
    return JSONResponse(
        content={"message": "Ссылка для восстановления пароля отправлена на ваш email"},
        status_code=200
    )

@router.get("/reset-password")
async def reset_password_page(request: Request, token: str):
    """
    Показать страницу для ввода нового пароля.
    
    Args:
        request: FastAPI Request объект
        token: Токен восстановления пароля
        
    Returns:
        HTMLResponse: Страница с формой для ввода нового пароля
        
    Raises:
        HTTPException: Если токен недействителен
    """
    # Проверяем токен
    user = await user_repo.verify_password_reset_token(token)
    if not user:
        raise HTTPException(
            status_code=400,
            detail="Ссылка недействительна или истекла"
        )
    
    return templates.TemplateResponse(
        "auth/reset_password.html",
        {"request": request, "token": token}
    )

@router.post("/reset-password")
async def reset_password(
    token: str = Form(...),
    new_password: str = Form(...),
):
    """
    Установка нового пароля по токену восстановления.
    
    Args:
        token: Токен восстановления пароля
        new_password: Новый пароль
        
    Returns:
        JSONResponse: Сообщение об успешном изменении пароля
        
    Raises:
        HTTPException: Если токен недействителен или истек
    """
    if len(new_password) < 6:
        raise HTTPException(
            status_code=400,
            detail="Пароль должен содержать минимум 6 символов"
        )
    
    success = await user_repo.reset_password_by_token(token, new_password)
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Ссылка недействительна или истекла"
        )
    
    from fastapi.responses import JSONResponse
    return JSONResponse(
        content={"message": "Пароль успешно изменен"},
        status_code=200
    )


@router.get("/register-choice")
async def register_choice_page(request: Request):
    """Страница выбора роли для регистрации"""
    return templates.TemplateResponse("auth/register_choice.html", {"request": request})


@router.get("/register")
async def register_page(request: Request):
    """Редирект на страницу выбора роли"""
    from starlette.responses import RedirectResponse
    return RedirectResponse(url="/auth/register-choice", status_code=303)


@router.get("/internal")
async def register_internal_page(request: Request):
    """Показать страницу регистрации для сотрудников (рекрутеров)"""
    return templates.TemplateResponse("auth/register_internal.html", {"request": request})


@router.get("/candidate")
async def register_candidate_page(request: Request):
    """Показать страницу регистрации для кандидатов"""
    return templates.TemplateResponse("auth/register_candidate.html", {"request": request})


@router.get("/contractor")
async def register_contractor_page(request: Request):
    """Показать страницу регистрации для подрядчиков (партнеров)"""
    return templates.TemplateResponse("auth/register_contractor.html", {"request": request})


async def process_registration(
    request: Request,
    email: str,
    password: str,
    confirm_password: str,
    first_name: str,
    last_name: str,
    phone: str,
    user_role: UserRole,
    template_name: str,
    middle_name: str = None,
    specialization: str = None,
    experience: str = None,
    resume: str = None,
    pd_consent: str = None,
):
    """
    Общая функция для обработки регистрации.
    
    Args:
        request: FastAPI Request объект
        email: Email пользователя
        password: Пароль пользователя
        confirm_password: Подтверждение пароля
        first_name: Имя
        last_name: Фамилия
        phone: Телефон
        user_role: Роль пользователя (определяется из URL)
        template_name: Имя шаблона для отображения ошибок
        middle_name: Отчество (опционально)
        specialization: Специализация (опционально)
        experience: Опыт работы (опционально)
        resume: Резюме или ссылка (опционально)
        pd_consent: Согласие на обработку ПД
        
    Returns:
        HTMLResponse: Страница успешной отправки заявки или страница с ошибкой
    """
    print(f"[REGISTRATION] Заявка на регистрацию: email={email}, role={user_role}")
    
    # Проверяем согласие на обработку персональных данных
    if not pd_consent or pd_consent != "on":
        return templates.TemplateResponse(
            template_name,
            {
                "request": request,
                "error": "Необходимо дать согласие на обработку персональных данных",
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
                "middle_name": middle_name,
                "phone": phone,
                "specialization": specialization,
                "experience": experience,
                "resume": resume
            }
        )
    
    if password != confirm_password:
        return templates.TemplateResponse(
            template_name,
            {
                "request": request,
                "error": "Пароли не совпадают",
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
                "middle_name": middle_name,
                "phone": phone,
                "specialization": specialization,
                "experience": experience,
                "resume": resume
            }
        )
    
    # Получаем IP-адрес клиента
    client_ip = request.client.host if request.client else None
    # Если за прокси, пытаемся получить реальный IP из заголовков
    if not client_ip or client_ip == "127.0.0.1":
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
        else:
            real_ip = request.headers.get("X-Real-IP")
            if real_ip:
                client_ip = real_ip
    
    # Получаем текущую дату и время
    from datetime import datetime
    consent_at = datetime.now().isoformat()
    
    # Создаем заявку
    request_obj = await registration_repository.create_request(
        email=email, 
        password=password,
        first_name=first_name,
        last_name=last_name,
        middle_name=middle_name,
        phone=phone,
        role=user_role,
        specialization=specialization,
        experience=experience,
        resume=resume,
        pd_consent=True,
        pd_consent_at=consent_at,
        pd_consent_email=email,
        pd_consent_ip=client_ip
    )
    if not request_obj:
        return templates.TemplateResponse(
            template_name,
            {
                "request": request,
                "error": "Пользователь с таким email уже существует или заявка уже подана",
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
                "middle_name": middle_name,
                "phone": phone,
                "specialization": specialization,
                "experience": experience,
                "resume": resume
            }
        )
    
    # Отправляем письмо для подтверждения email
    verification_link = f"http://omegahire.tech/auth/verify-email?token={request_obj.verification_token}"
    
    email_body = f"""
    <html>
    <body>
        <h2>Подтверждение регистрации на OmegaHire</h2>
        <p>Здравствуйте!</p>
        <p>Вы подали заявку на регистрацию в системе OmegaHire.</p>
        <p>Для подтверждения вашего email-адреса, пожалуйста, перейдите по ссылке:</p>
        <p><a href="{verification_link}">{verification_link}</a></p>
        <p>После подтверждения email администратор рассмотрит вашу заявку.</p>
        <br>
        <p>С уважением,<br>Команда OmegaHire</p>
    </body>
    </html>
    """
    
    try:
        success = await send_email_smtp(
            sender_email=settings.smtp_from_email,
            recipient_email=email,
            subject="Подтверждение регистрации на OmegaHire",
            body=email_body,
            html=True,
            smtp_host=settings.smtp_host,
            smtp_port=settings.smtp_port,
            smtp_username=settings.smtp_username,
            smtp_password=settings.smtp_password,
            use_tls=settings.smtp_use_tls,
            use_starttls=settings.smtp_use_starttls,
        )
        if success:
            print(f"[REGISTRATION] ✅ Письмо отправлено на {email}")
        else:
            print(f"[REGISTRATION] ⚠️ Не удалось отправить письмо на {email}")
    except Exception as e:
        print(f"[REGISTRATION] ❌ Ошибка при отправке письма: {e}")
    
    # Показываем страницу успеха
    return templates.TemplateResponse(
        "auth/register_success.html",
        {
            "request": request,
            "email": email
        }
    )


@router.post("/register")
async def register_request(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(...),
    phone: str = Form(...),
    middle_name: str = Form(None),
    role: str = Form(...),
    specialization: str = Form(None),
    experience: str = Form(None),
    resume: str = Form(None),
    pd_consent: str = Form(None),
):
    """
    Подать заявку на регистрацию (обратная совместимость - использует роль из формы).
    """
    try:
        user_role = UserRole(role)
        if user_role == UserRole.ADMIN:
            return templates.TemplateResponse(
                "auth/register_internal.html",
                {
                    "request": request,
                    "error": "Недопустимая роль",
                    "email": email,
                    "first_name": first_name,
                    "last_name": last_name,
                    "middle_name": middle_name,
                    "phone": phone,
                    "specialization": specialization,
                    "experience": experience,
                    "resume": resume
                }
            )
    except ValueError:
        return templates.TemplateResponse(
            "auth/register_internal.html",
            {
                "request": request,
                "error": "Недопустимая роль",
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
                "middle_name": middle_name,
                "phone": phone,
                "specialization": specialization,
                "experience": experience,
                "resume": resume
            }
        )
    
    return await process_registration(
        request=request,
        email=email,
        password=password,
        confirm_password=confirm_password,
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        user_role=user_role,
        template_name="auth/register_internal.html",
        middle_name=middle_name,
        specialization=specialization,
        experience=experience,
        resume=resume,
        pd_consent=pd_consent,
    )


@router.post("/internal")
async def register_internal_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(...),
    phone: str = Form(...),
    middle_name: str = Form(None),
    specialization: str = Form(None),
    experience: str = Form(None),
    resume: str = Form(None),
    pd_consent: str = Form(None),
):
    """Подать заявку на регистрацию для сотрудников (рекрутеров)"""
    return await process_registration(
        request=request,
        email=email,
        password=password,
        confirm_password=confirm_password,
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        user_role=UserRole.RECRUITER,
        template_name="auth/register_internal.html",
        middle_name=middle_name,
        specialization=specialization,
        experience=experience,
        resume=resume,
        pd_consent=pd_consent,
    )


@router.post("/candidate")
async def register_candidate_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(...),
    phone: str = Form(...),
    middle_name: str = Form(None),
    specialization: str = Form(None),
    experience: str = Form(None),
    resume: str = Form(None),
    pd_consent: str = Form(None),
):
    """Подать заявку на регистрацию для кандидатов"""
    return await process_registration(
        request=request,
        email=email,
        password=password,
        confirm_password=confirm_password,
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        user_role=UserRole.CANDIDATE,
        template_name="auth/register_candidate.html",
        middle_name=middle_name,
        specialization=specialization,
        experience=experience,
        resume=resume,
        pd_consent=pd_consent,
    )


@router.post("/contractor")
async def register_contractor_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(...),
    phone: str = Form(...),
    middle_name: str = Form(None),
    specialization: str = Form(None),
    experience: str = Form(None),
    resume: str = Form(None),
    pd_consent: str = Form(None),
):
    """Подать заявку на регистрацию для подрядчиков (партнеров)"""
    return await process_registration(
        request=request,
        email=email,
        password=password,
        confirm_password=confirm_password,
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        user_role=UserRole.CONTRACTOR,
        template_name="auth/register_contractor.html",
        middle_name=middle_name,
        specialization=specialization,
        experience=experience,
        resume=resume,
        pd_consent=pd_consent,
    )


@router.get("/verify-email")
async def verify_email(request: Request, token: str):
    """
    Подтверждение email пользователя по токену из письма.
    
    После подтверждения email администратор получает уведомление о новой заявке.
    
    Args:
        request: FastAPI Request объект
        token: Токен верификации из письма
        
    Returns:
        HTMLResponse: Страница ожидания одобрения администратором
        
    Raises:
        HTTPException: Если токен неверный или уже использован
    """
    print(f"[REGISTRATION] Подтверждение email: token={token}")
    
    request_obj = await registration_repository.verify_email(token)
    if not request_obj:
        raise HTTPException(
            status_code=400,
            detail="Неверный или уже использованный токен"
        )
    
    # Уведомляем администратора о новой заявке
    admin_link = f"http://omegahire.tech/admin/pending-registrations"
    
    email_body = f"""
    <html>
    <body>
        <h2>Новая заявка на регистрацию</h2>
        <p>Пользователь подтвердил свой email и ожидает одобрения:</p>
        <p><strong>Email:</strong> {request_obj.email}</p>
        <p><strong>Пароль:</strong> {request_obj.password}</p>
        <p>Для рассмотрения заявки перейдите в панель администратора:</p>
        <p><a href="{admin_link}">{admin_link}</a></p>
    </body>
    </html>
    """
    
    try:
        # Отправляем админу (можно настроить email админа в config)
        success = await send_email_smtp(
            sender_email=settings.smtp_from_email,
            recipient_email=settings.smtp_from_email,  # Отправляем себе
            subject="Новая заявка на регистрацию OmegaHire",
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
        print(f"[REGISTRATION] ❌ Ошибка отправки письма админу: {e}")
    
    # Показываем страницу ожидания
    return templates.TemplateResponse(
        "auth/email_verified.html",
        {"request": request}
    )


@router.post("/update-profile")
async def update_profile(
    request: Request,
    current_user=Depends(get_current_user_from_cookie),
):
    """
    Обновить профиль пользователя.
    
    Позволяет пользователю обновить свои данные в зависимости от роли:
    - RECRUITER: ФИО, телефон, опыт, специализацию, резюме
    - CANDIDATE: ФИО, телефон + профиль кандидата (grade, experience_years, stack, resume_url, bio)
    - CONTRACTOR: ФИО, телефон + профиль подрядчика (grade, experience_years, stack, hourly_rate_usd, is_available, portfolio_url, bio)
    
    Args:
        request: FastAPI Request объект с JSON телом
        current_user: Текущий авторизованный пользователь
        
    Returns:
        JSONResponse: Результат обновления профиля
        
    Raises:
        HTTPException: Если пользователь не авторизован
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        body = await request.json()
    except:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    from app.database.database import UserRole
    from app.database.candidate_profile_db import CandidateProfileRepository
    from app.models.users import ContractorProfile, Grade
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.database.database import engine
    
    # Обновляем базовые поля пользователя
    updated_user = await user_repo.update_profile(
        user_id=current_user.id,
        first_name=body.get("first_name"),
        last_name=body.get("last_name"),
        middle_name=body.get("middle_name"),
        phone=body.get("phone"),
        experience=body.get("experience"),
        specialization=body.get("specialization"),
        resume=body.get("resume"),
    )
    
    if not updated_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Обновляем профиль кандидата, если роль CANDIDATE
    if current_user.role == UserRole.CANDIDATE and "candidate_profile" in body:
        candidate_profile_repo = CandidateProfileRepository()
        profile_data = body["candidate_profile"]
        
        grade = None
        if profile_data.get("grade"):
            try:
                grade = Grade(profile_data["grade"])
            except ValueError:
                pass
        
        await candidate_profile_repo.create_or_update(
            user_id=current_user.id,
            grade=grade,
            experience_years=profile_data.get("experience_years"),
            stack=profile_data.get("stack"),
            resume_url=profile_data.get("resume_url"),
            bio=profile_data.get("bio"),
        )
    
    # Обновляем профиль подрядчика, если роль CONTRACTOR
    elif current_user.role == UserRole.CONTRACTOR and "contractor_profile" in body:
        profile_data = body["contractor_profile"]
        
        async with AsyncSession(engine) as session:
            result = await session.execute(
                select(ContractorProfile).where(ContractorProfile.user_id == current_user.id)
            )
            contractor_profile = result.scalar_one_or_none()
            
            grade = None
            if profile_data.get("grade"):
                try:
                    grade = Grade(profile_data["grade"])
                except ValueError:
                    pass
            
            if contractor_profile:
                # Обновляем существующий профиль
                if grade is not None:
                    contractor_profile.grade = grade
                if "experience_years" in profile_data:
                    contractor_profile.experience_years = profile_data["experience_years"]
                if "stack" in profile_data:
                    contractor_profile.stack = profile_data["stack"]
                if "hourly_rate_usd" in profile_data:
                    contractor_profile.hourly_rate_usd = profile_data["hourly_rate_usd"]
                if "is_available" in profile_data:
                    contractor_profile.is_available = profile_data["is_available"]
                if "portfolio_url" in profile_data:
                    contractor_profile.portfolio_url = profile_data["portfolio_url"]
                if "bio" in profile_data:
                    contractor_profile.bio = profile_data["bio"]
            else:
                # Создаем новый профиль
                contractor_profile = ContractorProfile(
                    user_id=current_user.id,
                    grade=grade,
                    experience_years=profile_data.get("experience_years"),
                    stack=profile_data.get("stack"),
                    hourly_rate_usd=profile_data.get("hourly_rate_usd"),
                    is_available=profile_data.get("is_available", True),
                    portfolio_url=profile_data.get("portfolio_url"),
                    bio=profile_data.get("bio"),
                )
                session.add(contractor_profile)
            
            await session.commit()
    
    from fastapi.responses import JSONResponse
    return JSONResponse(content={
        "ok": True,
        "message": "Профиль успешно обновлен"
    })


@router.get("/consent-personal-data", response_class=HTMLResponse)
async def consent_personal_data_page(request: Request):
    """
    Показать страницу «Согласие на обработку персональных данных».
    
    Returns:
        HTMLResponse: HTML страница с согласием на обработку персональных данных
    """
    return templates.TemplateResponse("auth/consent_personal_data.html", {"request": request})


@router.get("/policy-personal-data", response_class=HTMLResponse)
async def policy_personal_data_page(request: Request):
    """
    Показать страницу «Политика обработки и защиты персональных данных».
    
    Returns:
        HTMLResponse: HTML страница с политикой обработки персональных данных
    """
    return templates.TemplateResponse("auth/policy_personal_data.html", {"request": request})


@router.get("/download/pd-consent")
async def download_pd_consent():
    """
    Скачать документ «Согласие на обработку персональных данных».
    
    Returns:
        FileResponse: Файл Consent_Personal_Data_OmegaSolutionsGroup_2025-12-02.docx
    """
    # Используем абсолютный путь относительно корня проекта
    base_path = Path(__file__).resolve().parent.parent.parent
    file_path = base_path / "politic" / "Consent_Personal_Data_OmegaSolutionsGroup_2025-12-02.docx"
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Файл не найден")
    
    return FileResponse(
        path=str(file_path),
        filename="Согласие_на_обработку_персональных_данных.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )


@router.get("/download/pd-policy")
async def download_pd_policy():
    """
    Скачать документ «Политика обработки и защиты персональных данных».
    
    Returns:
        FileResponse: Файл Policy_Personal_Data_OmegaSolutionsGroup_2025-12-02.docx
    """
    # Используем абсолютный путь относительно корня проекта
    base_path = Path(__file__).resolve().parent.parent.parent
    file_path = base_path / "politic" / "Policy_Personal_Data_OmegaSolutionsGroup_2025-12-02.docx"
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Файл не найден")
    
    return FileResponse(
        path=str(file_path),
        filename="Политика_обработки_персональных_данных.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    