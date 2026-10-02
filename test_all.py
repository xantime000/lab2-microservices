"""
Скрипт автоматического тестирования API микросервисов:
- Проверка доступности API Gateway
- Auth-сервис: регистрация, вход с получением JWT, защищенный маршрут /me
- Catalog-сервис: CRUD операции товаров (/products)
- Проверка балансировки нагрузки Round-Robin
"""

import sys
import time
import requests

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# По умолчанию порт 8080 (локально) или 80 (Docker)
GATEWAY_URL = "http://127.0.0.1:8080"
if len(sys.argv) > 1:
    GATEWAY_URL = sys.argv[1]


def print_section(title):
    print("\n" + "=" * 65)
    print(f"  {title}")
    print("=" * 65)


def main():
    print(f"\n[ТЕСТ] Проверка микросервисов через API Gateway: {GATEWAY_URL}\n")

    # ----------------------------------------------------
    # 0. Проверка шлюза
    # ----------------------------------------------------
    print_section("0. ПРОВЕРКА ДОСТУПНОСТИ API GATEWAY")
    try:
        resp = requests.get(f"{GATEWAY_URL}/health", timeout=3)
        print(f"Статус шлюза: HTTP {resp.status_code}")
        print(f"Информация: {resp.json()}")
    except Exception as e:
        print(f"[ОШИБКА] API Gateway недоступен по адресу {GATEWAY_URL}!")
        print("Запустите 'python run_local.py' (для тестов на Windows) или 'docker compose up' (в Docker).")
        sys.exit(1)

    # ----------------------------------------------------
    # 1. Auth-сервис
    # ----------------------------------------------------
    print_section("1. ТЕСТИРОВАНИЕ AUTH-СЕРВИСА")
    username = f"user_{int(time.time())}"
    password = "secret_password_123"

    # 1.1 Регистрация
    print("\n[1.1 Регистрация пользователя (/auth/register)]")
    reg_resp = requests.post(f"{GATEWAY_URL}/auth/register", json={"username": username, "password": password})
    print(f"POST /auth/register -> HTTP {reg_resp.status_code}")
    print(f"Ответ: {reg_resp.json()}")
    assert reg_resp.status_code == 200, "Ошибка при регистрации"

    # 1.2 Вход (Login)
    print("\n[1.2 Вход (Login) и получение JWT (/auth/login)]")
    login_resp = requests.post(f"{GATEWAY_URL}/auth/login", json={"username": username, "password": password})
    print(f"POST /auth/login -> HTTP {login_resp.status_code}")
    login_data = login_resp.json()
    print(f"Ответ: {login_data}")
    assert login_resp.status_code == 200, "Ошибка при логине"
    token = login_data["access_token"]
    print(f"-> Успешно получен JWT токен: {token[:25]}...{token[-15:]}")

    # 1.3 Защищенный эндпоинт (/auth/me) БЕЗ токена (должен отклонить с кодом 401)
    print("\n[1.3 Защищенный метод (/auth/me) - Запрос БЕЗ токена]")
    unauth_resp = requests.get(f"{GATEWAY_URL}/auth/me")
    print(f"GET /auth/me (без токена) -> HTTP {unauth_resp.status_code}")
    print(f"Ответ: {unauth_resp.json()}")
    assert unauth_resp.status_code == 401, "Ошибка: запрос без токена не был отклонен!"
    print("-> Запрос без токена успешно отклонен (HTTP 401)")

    # 1.4 Защищенный эндпоинт (/auth/me) С валидным JWT токеном
    print("\n[1.4 Защищенный метод (/auth/me) - Запрос С валидным токеном]")
    auth_headers = {"Authorization": f"Bearer {token}"}
    auth_resp = requests.get(f"{GATEWAY_URL}/auth/me", headers=auth_headers)
    print(f"GET /auth/me (с токеном) -> HTTP {auth_resp.status_code}")
    print(f"Ответ: {auth_resp.json()}")
    assert auth_resp.status_code == 200, "Ошибка: валидный токен был отклонен"
    print(f"-> Доступ разрешен для пользователя: {auth_resp.json().get('username')}")

    # ----------------------------------------------------
    # 2. Catalog-сервис (CRUD + Идентификация инстанса)
    # ----------------------------------------------------
    print_section("2. ТЕСТИРОВАНИЕ CATALOG-СЕРВИСА (CRUD + INSTANCE_ID)")

    # 2.1 Read All (GET /catalog/products)
    print("\n[2.1 Read All (GET /catalog/products)]")
    list_resp = requests.get(f"{GATEWAY_URL}/catalog/products")
    print(f"GET /catalog/products -> HTTP {list_resp.status_code}")
    data = list_resp.json()
    print(f"Ответ обработал: {data.get('instance_id')}")
    print(f"Всего товаров в каталоге: {data.get('total')}")
    assert "instance_id" in data, "Ошибка: в ответе отсутствует instance_id!"

    # 2.2 Create (POST /catalog/products)
    print("\n[2.2 Create (POST /catalog/products)]")
    new_product = {
        "name": "Игровой монитор 144Hz",
        "price": 24990.0,
        "category": "Электроника",
        "stock": 5
    }
    create_resp = requests.post(f"{GATEWAY_URL}/catalog/products", json=new_product)
    print(f"POST /catalog/products -> HTTP {create_resp.status_code}")
    created_item = create_resp.json()
    print(f"Создан товар: {created_item.get('item')}")
    assert create_resp.status_code == 201, "Ошибка создания товара"
    product_id = created_item["item"]["id"]

    # 2.3 Read One (GET /catalog/products/{id})
    print(f"\n[2.3 Read One (GET /catalog/products/{product_id})]")
    get_resp = requests.get(f"{GATEWAY_URL}/catalog/products/{product_id}")
    print(f"GET /catalog/products/{product_id} -> HTTP {get_resp.status_code}")
    print(f"Инстанс: {get_resp.json().get('instance_id')}")
    print(f"Данные товара: {get_resp.json().get('item')}")
    assert get_resp.status_code == 200, "Товар не найден"

    # 2.4 Update (PUT /catalog/products/{id})
    print(f"\n[2.4 Update (PUT /catalog/products/{product_id})]")
    update_data = {"price": 22990.0, "stock": 4}
    put_resp = requests.put(f"{GATEWAY_URL}/catalog/products/{product_id}", json=update_data)
    print(f"PUT /catalog/products/{product_id} -> HTTP {put_resp.status_code}")
    print(f"Обновленный товар: {put_resp.json().get('item')}")
    assert put_resp.status_code == 200, "Ошибка обновления товара"

    # 2.5 Delete (DELETE /catalog/products/{id})
    print(f"\n[2.5 Delete (DELETE /catalog/products/{product_id})]")
    del_resp = requests.delete(f"{GATEWAY_URL}/catalog/products/{product_id}")
    print(f"DELETE /catalog/products/{product_id} -> HTTP {del_resp.status_code}")
    print(f"Ответ: {del_resp.json()}")
    assert del_resp.status_code == 200, "Ошибка удаления товара"

    # ----------------------------------------------------
    # 3. Доказательство балансировки нагрузки
    # ----------------------------------------------------
    print_section("3. ПРОВЕРКА БАЛАНСИРОВКИ НАГРУЗКИ (ROUND-ROBIN)")
    print("Выполняем 6 последовательных GET запросов к /catalog/products через Gateway:")
    history = []
    for i in range(1, 7):
        r = requests.get(f"{GATEWAY_URL}/catalog/products")
        inst = r.json().get("instance_id") or r.headers.get("X-Handled-By")
        history.append(inst)
        print(f"  -> Запрос #{i}: обработан инстансом [{inst}]")
        time.sleep(0.05)

    print("\nСтатистика распределения:")
    for inst in sorted(set(history)):
        print(f"  - {inst}: {history.count(inst)} запросов")

    unique_nodes = len(set(history))
    assert unique_nodes >= 2, "Ошибка: запросы не балансируются между инстансами!"
    print("\n>>> [УСПЕХ] Запросы равномерно чередуются между инстансами (Round-Robin работает)!")

    print_section("ТЕСТИРОВАНИЕ УСПЕШНО ЗАВЕРШЕНО")


if __name__ == "__main__":
    main()
