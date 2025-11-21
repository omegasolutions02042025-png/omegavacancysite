from click.types import UUID
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, Response
from starlette.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from passlib.hash import bcrypt
from fastapi.templating import Jinja2Templates
import os

from app.core.security import auth as authx
from app.core.current_user import get_current_user_from_cookie
from app.models.user import UserCreate
from fastapi import HTTPException
from app.database.user_db import UserRepository
from pathlib import Path

router = APIRouter(prefix="/auth", tags=["Аутентификация"])
user_repo = UserRepository()
templates = Jinja2Templates(directory="templates")


@router.post("/register")
async def register(user: UserCreate):
    email = user.email
    password = user.password
    print(email, password)
    status = await user_repo.create_user(email=email, password=password)
    if not status:
        print("User already exists")
        return HTTPException(status_code=400, detail="User already exists")

    token = authx.create_access_token(uid=str(status.id))

    response = RedirectResponse("/auth/profile", status_code=303)
    response.set_cookie(
        "access_token",
        token,
        httponly=True,
        samesite="lax",
        path="/"
    )

    return response



@router.post("/login")
async def login(email: str = Form(...), password: str = Form(...)):
    user = await user_repo.authenticate(email, password)
    if not user:
        return HTTPException(status_code=400, detail="Incorrect email or password")
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

@router.get("/profile", response_class=HTMLResponse)
async def profile(
    request: Request,
    current_user=Depends(get_current_user_from_cookie),
):
    if not current_user:
        return RedirectResponse("/auth/login", status_code=303)
    
    return templates.TemplateResponse(
        "auth/profile.html",
        {
            "request": request,
            "user_id": current_user.id,
            "user_email": current_user.email,
            "telegram_username": current_user.work_telegram,
            "linked_email" : current_user.work_email,
            'user_id' : current_user.id # ВАЖНО — сюда привязываем email
        },
    )



@router.get("/register")
async def register_page(request: Request):
  """Показать страницу регистрации"""
  return templates.TemplateResponse("auth/register.html", {"request": request})


@router.get("/login")
async def login_page(request: Request):
  """Показать страницу логина"""
  return templates.TemplateResponse("auth/login.html", {"request": request})

@router.get("/logout")
async def logout():
    resp = RedirectResponse("/auth/login", status_code=303)
    # ВАЖНО: то же имя и path, что и при установке
    resp.delete_cookie("access_token", path="/")
    return resp