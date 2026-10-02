"""
Auth-сервис (FastAPI)
Соответствие чек-листу и Шагу 1:
1. Регистрация: POST /register (принимает username, password, сохраняет в in-memory словаре)
2. Вход (Login): POST /login (проверяет учетные данные, возвращает JWT-токен)
3. Защищенный эндпоинт: GET /me (требует заголовок Authorization: Bearer <token>)
4. Хэширование через passlib, токены через PyJWT
5. Service Discovery (Consul): авто-регистрация при старте и дерегистрация при остановке
"""

import os
import sys
import datetime
from contextlib import asynccontextmanager
from typing import Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import jwt
import requests
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel

# Хэширование через passlib (как указано в задании)
try:
    from passlib.hash import pbkdf2_sha256
    def hash_password(password: str) -> str:
        return pbkdf2_sha256.hash(password)
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        return pbkdf2_sha256.verify(plain_password, hashed_password)
except Exception:
    import hashlib
    def hash_password(password: str) -> str:
        return hashlib.sha256(password.encode("utf-8")).hexdigest()
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        return hashlib.sha256(plain_password.encode("utf-8")).hexdigest() == hashed_password

SERVICE_NAME = "auth"
SERVICE_HOST = os.getenv("SERVICE_HOST", "127.0.0.1")
SERVICE_PORT = int(os.getenv("PORT", "5001"))
CONSUL_HOST = os.getenv("CONSUL_HOST", "127.0.0.1")
CONSUL_PORT = int(os.getenv("CONSUL_PORT", "8500"))
JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-key-student-lab-2")
JWT_ALGORITHM = "HS256"

# In-memory хранилище пользователей (словарь Python): username -> hashed_password
users_db = {}


def register_in_consul():
    """Авто-регистрация сервиса в Consul через HTTP API при старте"""
    consul_url = f"http://{CONSUL_HOST}:{CONSUL_PORT}/v1/agent/service/register"
    service_id = f"{SERVICE_NAME}-{SERVICE_PORT}"
    payload = {
        "ID": service_id,
        "Name": SERVICE_NAME,
        "Address": SERVICE_HOST,
        "Port": SERVICE_PORT,
        "Check": {
            "HTTP": f"http://{SERVICE_HOST}:{SERVICE_PORT}/health",
            "Interval": "10s",
            "Timeout": "3s",
            "DeregisterCriticalServiceAfter": "1m"
        }
    }
    try:
        resp = requests.put(consul_url, json=payload, timeout=2)
        if resp.status_code == 200:
            print(f"[Consul] Сервис {service_id} успешно зарегистрирован в Consul!")
        else:
            print(f"[Consul] Ошибка регистрации: {resp.status_code} {resp.text}")
    except Exception:
        print(f"[Consul] Consul недоступен ({CONSUL_HOST}:{CONSUL_PORT}). Работаем локально.")


def deregister_from_consul():
    """Авто-дерегистрация сервиса из Consul при корректной остановке"""
    service_id = f"{SERVICE_NAME}-{SERVICE_PORT}"
    consul_url = f"http://{CONSUL_HOST}:{CONSUL_PORT}/v1/agent/service/deregister/{service_id}"
    try:
        requests.put(consul_url, timeout=2)
        print(f"[Consul] Сервис {service_id} успешно разрегистрирован из Consul.")
    except Exception:
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    register_in_consul()
    yield
    deregister_from_consul()


app = FastAPI(title="Auth Service", lifespan=lifespan)


class UserCredentials(BaseModel):
    username: str
    password: str


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": SERVICE_NAME,
        "port": SERVICE_PORT
    }


# ----------------------------------------------------
# 1. РЕГИСТРАЦИЯ: POST /register и /auth/register
# ----------------------------------------------------
@app.post("/register")
@app.post("/auth/register")
def register(creds: UserCredentials):
    """Эндпоинт регистрации пользователя в in-memory словаре"""
    if creds.username in users_db:
        raise HTTPException(status_code=400, detail="Пользователь уже существует")
    
    users_db[creds.username] = hash_password(creds.password)
    return {
        "status": "ok",
        "message": f"Пользователь '{creds.username}' успешно зарегистрирован"
    }


# ----------------------------------------------------
# 2. ВХОД (LOGIN): POST /login и /auth/login
# ----------------------------------------------------
@app.post("/login")
@app.post("/auth/login")
def login(creds: UserCredentials):
    """Эндпоинт входа, возвращающий валидный JWT-токен"""
    hashed = users_db.get(creds.username)
    if not hashed or not verify_password(creds.password, hashed):
        raise HTTPException(status_code=401, detail="Неверное имя пользователя или пароль")
    
    payload = {
        "sub": creds.username,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=2),
        "iat": datetime.datetime.utcnow()
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": 7200
    }


# ----------------------------------------------------
# 3. ЗАЩИЩЕННЫЙ ЭНДПОИНТ: GET /me и /auth/me
# ----------------------------------------------------
@app.get("/me")
@app.get("/auth/me")
@app.get("/verify")
@app.get("/auth/verify")
def get_current_user(authorization: Optional[str] = Header(None)):
    """
    Защищенный метод (/me):
    - Отклоняет запросы без токена с ошибкой 401
    - Принимает запросы с валидным JWT токеном в заголовке Authorization: Bearer <token>
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Заголовок Authorization отсутствует")
    
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Неверный формат Authorization. Ожидается: Bearer <token>")
    
    token = parts[1]
    try:
        decoded = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return {
            "status": "authorized",
            "username": decoded["sub"],
            "expires_at": decoded.get("exp"),
            "message": f"Доступ разрешен для пользователя {decoded['sub']}!"
        }
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Срок действия JWT токена истек")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Недействительный JWT токен")


if __name__ == "__main__":
    import uvicorn
    print(f"Запуск {SERVICE_NAME} на порту {SERVICE_PORT}...")
    uvicorn.run(app, host="0.0.0.0", port=SERVICE_PORT)
