# webapp/routers/auth.py
import random
import logging
import string
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from db import async_session_maker, User
from webapp.core.mail import send_reset_code
from webapp.core.security import get_password_hash, verify_password, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
from datetime import timedelta, datetime

router = APIRouter()
templates = Jinja2Templates(directory="webapp/templates")

# Зависимость для получения сессии БД
async def get_db():
    async with async_session_maker() as session:
        yield session

# --- ГЕНЕРАЦИЯ ID ДЛЯ WEB ---
async def generate_web_user_id(session: AsyncSession) -> int:
    """
    Генерирует отрицательный ID, чтобы не конфликтовать с Telegram ID.
    Проверяет, свободен ли ID.
    """
    while True:
        # Генерируем ID от -1 до -1 000 000 000
        new_id = random.randint(-1000000000, -1)
        result = await session.execute(select(User).where(User.user_id == new_id))
        if not result.scalar_one_or_none():
            return new_id

# --- СТРАНИЦЫ (GET) ---

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@router.get("/logout")
async def logout_user():
    # Перенаправляем на страницу входа
    response = RedirectResponse(url="/login", status_code=302)
    # Удаляем куку с токеном
    response.delete_cookie(key="access_token")
    return response
@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    return templates.TemplateResponse("forgot_password.html", {"request": request})

@router.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(request: Request):
    return templates.TemplateResponse("reset_password.html", {"request": request})

@router.post("/register")
async def register_user(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    logging.info(f"Attempting to register user with email: {password}")
    
    # 1. Проверяем, есть ли такой email
    existing_user = await db.execute(select(User).where(User.email == email))
    if existing_user.scalar_one_or_none():
        return templates.TemplateResponse("register.html", {
            "request": request, 
            "error": "Пользователь с таким Email уже существует"
        })

    # 2. Генерируем ID и хеш
    new_user_id = await generate_web_user_id(db)
    hashed_password = get_password_hash(password)

    # 3. Создаем пользователя
    new_user = User(
        user_id=new_user_id,
        email=email,
        password_hash=hashed_password,
        full_name=full_name,
        username=email.split('@')[0], # Временное решение
        has_received_trial=False
    )
    
    db.add(new_user)
    await db.commit()
    
    # 4. Сразу логиним (создаем токен) и редиректим
    access_token = create_access_token(
        data={"sub": str(new_user.user_id), "email": new_user.email},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(key="access_token", value=f"Bearer {access_token}", httponly=True)
    return response

@router.post("/login")
async def login_user(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    # 1. Ищем пользователя
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    
    # 2. Проверка пароля
    if not user or not user.password_hash or not verify_password(password, user.password_hash):
        return templates.TemplateResponse("login.html", {
            "request": request, 
            "error": "Неверный Email или пароль"
        })
    
    # 3. Создаем токен
    access_token = create_access_token(
        data={"sub": str(user.user_id), "email": user.email},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    response = RedirectResponse(url="/", status_code=302)
    # httponly=True защищает от кражи кук через JS
    response.set_cookie(key="access_token", value=f"Bearer {access_token}", httponly=True)
    return response


@router.post("/forgot-password")
async def send_reset_email(
    request: Request,
    email: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    # 1. Ищем пользователя
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user:
        # Для безопасности можно писать "Если почта существует, мы отправили код", 
        # но для удобства скажем правду
        return templates.TemplateResponse("forgot_password.html", {
            "request": request, "error": "Пользователь с таким Email не найден"
        })

    # 2. Генерируем код (6 цифр)
    code = ''.join(random.choices(string.digits, k=6))
    
    # 3. Сохраняем в БД (время жизни 15 мин)
    user.reset_code = code
    user.reset_code_expire = datetime.now() + timedelta(minutes=15)
    await db.commit()

    # 4. Отправляем письмо
    try:
        await send_reset_code(email, code)
    except Exception as e:
        return templates.TemplateResponse("forgot_password.html", {
            "request": request, "error": f"Ошибка отправки письма: {e}"
        })

    # 5. Перенаправляем на ввод кода
    return templates.TemplateResponse("reset_password.html", {
        "request": request, 
        "email": email, # Передаем email, чтобы юзеру не вводить его снова
        "message": "Код отправлен на вашу почту!"
    })


@router.post("/reset-password")
async def process_reset_password(
    request: Request,
    email: str = Form(...),
    code: str = Form(...),
    new_password: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    # 1. Ищем пользователя
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user:
        return templates.TemplateResponse("reset_password.html", {
            "request": request, "email": email, "error": "Пользователь не найден"
        })

    # 2. Проверяем код и время
    if user.reset_code != code:
        return templates.TemplateResponse("reset_password.html", {
            "request": request, "email": email, "error": "Неверный код"
        })
    
    if not user.reset_code_expire or user.reset_code_expire < datetime.now():
        return templates.TemplateResponse("reset_password.html", {
            "request": request, "email": email, "error": "Срок действия кода истек"
        })

    # 3. Меняем пароль
    user.password_hash = get_password_hash(new_password)
    
    # 4. Очищаем код (чтобы нельзя было использовать повторно)
    user.reset_code = None
    user.reset_code_expire = None
    await db.commit()

    # 5. Отправляем на логин
    return templates.TemplateResponse("login.html", {
        "request": request, 
        "message": "Пароль успешно изменен! Теперь войдите."
    })