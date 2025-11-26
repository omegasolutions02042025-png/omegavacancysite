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
from app.database.database import create_tables
from app.database.user_db import UserRepository
from .core.scheduler import start_scheduler
from app.core.current_user import get_current_user_from_cookie
from app.core.telethon_check import manager
from app.routes.auth import router as auth_router
from app.core.email_listener import email_listener
import logging

logging.basicConfig(level=logging.DEBUG)


user_repo = UserRepository()

scheduler = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global scheduler

    # ---- STARTUP ----
    #scheduler = start_scheduler()
    await create_tables()
    await manager.start_all_sessions()
    asyncio.create_task(email_listener.start_all())
    print("[LIFESPAN] startup complete, email listeners started")

    try:
        yield
    finally:
        # ---- SHUTDOWN ----
        # if scheduler:
        #     await scheduler.shutdown()
        #await manager.shutdown()
        await email_listener.shutdown()
        print("[LIFESPAN] shutdown complete, email listeners stopped")
        

app = FastAPI(title="OmegaVac API", lifespan=lifespan)




# Use absolute path to templates directory
templates_dir = str(Path(__file__).resolve().parent / "templates")
templates = Jinja2Templates(directory=templates_dir)
app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static",
)


app.mount("/static", StaticFiles(directory='static'), name="static")



app.include_router(upload_router)
app.include_router(sverka_router)
app.include_router(vacancy_router)
app.include_router(download_wl_router)
app.include_router(dropdown_router)
app.include_router(auth_router)
app.include_router(email_router)
app.include_router(send_mails_router)
app.include_router(telegram_link_router)
app.include_router(websock_router)
app.include_router(notify_router)
app.include_router(candidate_router)

@app.get("/", response_class=HTMLResponse)
async def root(request: Request, current_user=Depends(get_current_user_from_cookie)):
    if current_user:
        return templates.TemplateResponse("index.html", {"request": request, "user_email": current_user.email, "user_id": current_user.id})
    else:
        return templates.TemplateResponse("index.html", {"request": request})


