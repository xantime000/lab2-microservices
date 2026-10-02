"""
Микросервис каталога товаров (FastAPI)
- CRUD операции с товарами (/products)
- Использование базы данных SQLite
- Идентификация инстанса (INSTANCE_NAME)
- Интеграция с Consul Service Discovery
"""

import os
import sys
import sqlite3
from contextlib import asynccontextmanager
from typing import Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

SERVICE_NAME = "catalog"
SERVICE_HOST = os.getenv("SERVICE_HOST", "127.0.0.1")
SERVICE_PORT = int(os.getenv("PORT", "5002"))
INSTANCE_NAME = os.getenv("INSTANCE_NAME", os.getenv("INSTANCE_ID", f"catalog-{SERVICE_PORT}"))
INSTANCE_ID = INSTANCE_NAME
CONSUL_HOST = os.getenv("CONSUL_HOST", "127.0.0.1")
CONSUL_PORT = int(os.getenv("CONSUL_PORT", "8500"))

# База данных SQLite (общая для инстансов)
DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "products.db")
DB_PATH = os.getenv("DB_PATH", DEFAULT_DB_PATH)


def get_db():
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                category TEXT DEFAULT 'Общее',
                stock INTEGER DEFAULT 1
            )
        """)
        cursor.execute("SELECT COUNT(*) FROM products")
        if cursor.fetchone()[0] == 0:
            cursor.executemany("""
                INSERT INTO products (name, price, category, stock)
                VALUES (?, ?, ?, ?)
            """, [
                ("Игровой ноутбук", 85000.0, "Электроника", 10),
                ("Беспроводная мышь", 1800.0, "Аксессуары", 45),
                ("Механическая клавиатура", 4200.0, "Аксессуары", 20)
            ])
            conn.commit()


def register_in_consul():
    """Авто-регистрация инстанса в Consul при запуске"""
    consul_url = f"http://{CONSUL_HOST}:{CONSUL_PORT}/v1/agent/service/register"
    service_unique_id = f"{SERVICE_NAME}-{INSTANCE_ID}"
    payload = {
        "ID": service_unique_id,
        "Name": SERVICE_NAME,
        "Address": SERVICE_HOST,
        "Port": SERVICE_PORT,
        "Tags": [INSTANCE_ID, "catalog"],
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
            print(f"[Consul] Инстанс {service_unique_id} успешно зарегистрирован в Consul!")
        else:
            print(f"[Consul] Ошибка регистрации: {resp.status_code} {resp.text}")
    except Exception:
        print(f"[Consul] Consul недоступен ({CONSUL_HOST}:{CONSUL_PORT}). Работаем локально без него.")


def deregister_from_consul():
    """Авто-дерегистрация инстанса из Consul при выключении"""
    service_unique_id = f"{SERVICE_NAME}-{INSTANCE_ID}"
    consul_url = f"http://{CONSUL_HOST}:{CONSUL_PORT}/v1/agent/service/deregister/{service_unique_id}"
    try:
        requests.put(consul_url, timeout=2)
        print(f"[Consul] Инстанс {service_unique_id} успешно снят с регистрации.")
    except Exception:
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    register_in_consul()
    yield
    deregister_from_consul()


app = FastAPI(title=f"Catalog Service ({INSTANCE_ID})", lifespan=lifespan)


class ProductCreate(BaseModel):
    name: str
    price: float
    category: str = "Общее"
    stock: int = 1


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    price: Optional[float] = None
    category: Optional[str] = None
    stock: Optional[int] = None


@app.middleware("http")
async def add_instance_header(request, call_next):
    response = await call_next(request)
    response.headers["X-Handled-By"] = INSTANCE_ID
    return response


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": SERVICE_NAME,
        "instance_id": INSTANCE_ID,
        "port": SERVICE_PORT
    }


# ============================================================
# CRUD ЭНДПОИНТЫ (доступны по путям /catalog/products и /products)
# ============================================================

# 1. READ ALL (GET)
@app.get("/catalog/products")
@app.get("/catalog/products/")
@app.get("/products")
@app.get("/products/")
def list_products():
    """
    [Read All] Получение списка товаров.
    Обязательно возвращает instance_id в ответе для доказательства балансировки.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products ORDER BY id")
        items = [dict(row) for row in cursor.fetchall()]
        return {
            "instance_id": INSTANCE_ID,
            "handled_by": INSTANCE_ID,
            "total": len(items),
            "items": items
        }


# 2. READ ONE (GET)
@app.get("/catalog/products/{product_id}")
@app.get("/products/{product_id}")
def get_product(product_id: int):
    """
    [Read One] Получение товара по ID.
    Обязательно возвращает instance_id в ответе.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Товар с id={product_id} не найден")
        return {
            "instance_id": INSTANCE_ID,
            "handled_by": INSTANCE_ID,
            "item": dict(row)
        }


# 3. CREATE (POST)
@app.post("/catalog/products", status_code=201)
@app.post("/catalog/products/", status_code=201)
@app.post("/products", status_code=201)
@app.post("/products/", status_code=201)
def create_product(product: ProductCreate):
    """[Create] Добавление нового товара"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO products (name, price, category, stock)
            VALUES (?, ?, ?, ?)
        """, (product.name, product.price, product.category, product.stock))
        conn.commit()
        new_id = cursor.lastrowid
        cursor.execute("SELECT * FROM products WHERE id = ?", (new_id,))
        created = dict(cursor.fetchone())

    return {
        "instance_id": INSTANCE_ID,
        "message": "Товар успешно добавлен",
        "item": created
    }


# 4. UPDATE (PUT)
@app.put("/catalog/products/{product_id}")
@app.put("/products/{product_id}")
def update_product(product_id: int, product: ProductUpdate):
    """[Update] Обновление товара по ID"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Товар с id={product_id} не найден")

        current = dict(row)
        name = product.name if product.name is not None else current["name"]
        price = product.price if product.price is not None else current["price"]
        category = product.category if product.category is not None else current["category"]
        stock = product.stock if product.stock is not None else current["stock"]

        cursor.execute("""
            UPDATE products
            SET name = ?, price = ?, category = ?, stock = ?
            WHERE id = ?
        """, (name, price, category, stock, product_id))
        conn.commit()
        cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        updated = dict(cursor.fetchone())

    return {
        "instance_id": INSTANCE_ID,
        "message": "Товар успешно обновлен",
        "item": updated
    }


# 5. DELETE (DELETE)
@app.delete("/catalog/products/{product_id}")
@app.delete("/products/{product_id}")
def delete_product(product_id: int):
    """[Delete] Удаление товара по ID"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Товар с id={product_id} не найден")

        cursor.execute("DELETE FROM products WHERE id = ?", (product_id,))
        conn.commit()

    return {
        "instance_id": INSTANCE_ID,
        "message": f"Товар '{dict(row)['name']}' успешно удален",
        "deleted_id": product_id
    }


if __name__ == "__main__":
    import uvicorn
    print(f"Запуск {SERVICE_NAME} ({INSTANCE_ID}) на порту {SERVICE_PORT}...")
    uvicorn.run(app, host="0.0.0.0", port=SERVICE_PORT)
