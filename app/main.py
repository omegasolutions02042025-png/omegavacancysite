from contextlib import asynccontextmanager
import asyncio
from pathlib import Path
from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from app.routes.upload import router as upload_router
from app.routes.sverka import router as sverka_router
from app.routes.vacancy import router as vacancy_router
from app.routes.download_wl import router as download_wl_router
from app.routes.dropdown import router as dropdown_router
from app.routes.email import router as email_router
from app.routes.send_mails import router as send_mails_router
from app.routes.telegram_link import router as telegram_link_router
from app.routes.websock import router as websock_router
from app.routes.notify import router as notify_router
from app.routes.candidate import router as candidate_router
from app.routes.chat import router as chat_router
from app.routes.photo import router as photo_router
from app.routes.currency import router as currency_router
from app.database.database import create_tables, get_db
from app.database.user_db import UserRepository
from .core.scheduler import start_scheduler
from app.core.current_user import get_current_user_from_cookie
from app.core.telethon_check import manager
from app.routes.auth import router as auth_router
from app.routes.admin import router as admin_router
from app.core.email_listener import email_listener
from app.services.currency_service import CurrencyService
from app.core.security import config
import logging

logging.basicConfig(level=logging.DEBUG)


user_repo = UserRepository()

scheduler = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global scheduler

    # ---- STARTUP ----
    scheduler = start_scheduler()
    await create_tables()
    
    # Инициализация курсов валют при старте
    async for session in get_db():
        try:
            await CurrencyService.ensure_rates_available(session)
            print("[LIFESPAN] Exchange rates initialized")
        except Exception as e:
            print(f"[LIFESPAN] Error initializing exchange rates: {e}")
        break
    
    await manager.start_all_sessions()
    asyncio.create_task(email_listener.start_all())
    print("[LIFESPAN] startup complete, email listeners started")

    try:
        yield
    finally:
        # ---- SHUTDOWN ----
        if scheduler:
            scheduler.shutdown()
        #await manager.shutdown()
        await email_listener.shutdown()
        print("[LIFESPAN] shutdown complete, email listeners stopped")
        

app = FastAPI(title="OmegaVac API", lifespan=lifespan)


@app.middleware("http")
async def archived_user_logout_middleware(request: Request, call_next):
    response = await call_next(request)
    if getattr(request.state, "force_logout", False):
        response.delete_cookie(
            config.JWT_ACCESS_COOKIE_NAME,
            path="/",
            samesite="lax",
        )
    return response




# Use absolute path to templates directory
templates_dir = str(Path(__file__).resolve().parent / "templates")
templates = Jinja2Templates(directory=templates_dir)

# Use absolute paths for static files
static_dir = str(Path(__file__).resolve().parent / "static")
media_dir = str(Path(__file__).resolve().parent / "media")

app.mount(
    "/static",
    StaticFiles(directory=static_dir),
    name="static",
)

app.mount(
    "/media",
    StaticFiles(directory=media_dir),
    name="media",
)



app.include_router(upload_router)
app.include_router(sverka_router)
app.include_router(vacancy_router)
app.include_router(download_wl_router)
app.include_router(dropdown_router)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(email_router)
app.include_router(send_mails_router)
app.include_router(telegram_link_router)
app.include_router(websock_router)
app.include_router(notify_router)
app.include_router(candidate_router)
app.include_router(chat_router)
app.include_router(photo_router)
app.include_router(currency_router)

@app.get("/ui-kit", response_class=HTMLResponse)
async def ui_kit(request: Request):
    return templates.TemplateResponse("ui_kit.html", {"request": request})

@app.get("/dashboard-v2", response_class=HTMLResponse)
async def dashboard_v2(request: Request):
    # Mock data for sidebar and header logic
    return templates.TemplateResponse("dashboard_v2.html", {
        "request": request, 
        "user_id": 1, 
        "unread_messages_count": 3
    })

@app.get("/", response_class=HTMLResponse)
async def root(request: Request, current_user=Depends(get_current_user_from_cookie)):
    if current_user:
        return templates.TemplateResponse("index.html", {"request": request, "user_email": current_user.email, "user_id": current_user.id})
    else:
        return templates.TemplateResponse("index.html", {"request": request})


