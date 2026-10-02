"""
Скрипт запуска всей лабораторной работы локально на Windows БЕЗ Docker.
Запускает:
1. Auth-сервис на порту 5001
2. Catalog-сервис (Инстанс 1) на порту 5002
3. Catalog-сервис (Инстанс 2) на порту 5003
4. Локальный API Gateway на порту 8080
"""

import os
import sys
import time
import subprocess
import signal

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON_EXE = sys.executable

processes = []

def start_service(name, script_path, env_vars=None):
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    if env_vars:
        env.update(env_vars)
    
    print(f"[Запуск] {name}...")
    p = subprocess.Popen(
        [PYTHON_EXE, script_path],
        cwd=os.path.dirname(script_path),
        env=env
    )
    processes.append((name, p))
    return p

def main():
    print("=" * 65)
    print("  ЗАПУСК ЛАБОРАТОРНОЙ РАБОТЫ №2 (МИКРОСЕРВИСЫ И ШЛЮЗ)")
    print("  Режим: Локальный запуск на Windows (без Docker)")
    print("=" * 65)

    try:
        # 1. Запуск сервиса авторизации
        start_service(
            "Auth Service",
            os.path.join(CURRENT_DIR, "auth_service", "app.py"),
            {"PORT": "5001", "SERVICE_HOST": "127.0.0.1"}
        )

        db_path = os.path.join(CURRENT_DIR, "products.db")

        # 2. Запуск первого инстанса каталога (catalog-1)
        start_service(
            "Catalog Service (catalog-1)",
            os.path.join(CURRENT_DIR, "catalog_service", "app.py"),
            {
                "PORT": "5002",
                "SERVICE_HOST": "127.0.0.1",
                "INSTANCE_NAME": "catalog-1",
                "INSTANCE_ID": "catalog-1",
                "DB_PATH": db_path
            }
        )

        # 3. Запуск второго инстанса каталога (catalog-2)
        start_service(
            "Catalog Service (catalog-2)",
            os.path.join(CURRENT_DIR, "catalog_service", "app.py"),
            {
                "PORT": "5003",
                "SERVICE_HOST": "127.0.0.1",
                "INSTANCE_NAME": "catalog-2",
                "INSTANCE_ID": "catalog-2",
                "DB_PATH": db_path
            }
        )

        # 4. Запуск локального API Gateway
        time.sleep(1)
        start_service(
            "API Gateway",
            os.path.join(CURRENT_DIR, "local_gateway.py")
        )

        time.sleep(2)
        print("\n" + "=" * 65)
        print("  ВСЕ СЕРВИСЫ УСПЕШНО ЗАПУЩЕНЫ!")
        print("=" * 65)
        print("  -> API Gateway:      http://127.0.0.1:8080")
        print("  -> Auth Service:     http://127.0.0.1:5001/docs (Swagger)")
        print("  -> Catalog Node 1:   http://127.0.0.1:5002/docs (Swagger)")
        print("  -> Catalog Node 2:   http://127.0.0.1:5003/docs (Swagger)")
        print("=" * 65)
        print("  Для проверки запустите автотест: python test_all.py")
        print("  Для остановки всех сервисов нажмите Ctrl + C")
        print("=" * 65 + "\n")

        # Ожидание прерывания пользователем
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nОстановка всех сервисов...")
        for name, p in processes:
            print(f"Останавливаю {name}...")
            p.terminate()
        print("Все сервисы остановлены.")

if __name__ == "__main__":
    main()
