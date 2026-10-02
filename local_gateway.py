"""
Локальный API Gateway (эмулятор Nginx для Windows)
Точно повторяет поведение Nginx из Шага 4:
- /auth/* -> проксирует на сервис auth (порт 5001)
- /catalog/* -> проксирует на upstream catalog (порты 5002 и 5003) с Round-Robin
- Отказоустойчивость: если один из инстансов не отвечает, запрос идет на живой
"""

import os
import sys
import itertools
import requests
from fastapi import FastAPI, Request, Response
import uvicorn

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

app = FastAPI(title="Local API Gateway (Nginx Emulator)")

AUTH_BACKEND = "http://127.0.0.1:5001"
CATALOG_BACKENDS = [
    "http://127.0.0.1:5002",
    "http://127.0.0.1:5003"
]

catalog_cycle = itertools.cycle(CATALOG_BACKENDS)


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "gateway": "Local Python API Gateway",
        "catalog_backends": CATALOG_BACKENDS
    }


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_request(request: Request, path: str):
    full_path = "/" + path
    body = await request.body()
    headers = dict(request.headers)
    headers.pop("host", None)
    headers.pop("content-length", None)

    # 1. Проксирование /auth/ на Auth-сервис
    if full_path.startswith("/auth"):
        sub_path = full_path[len("/auth"):]  # /register, /login, /me
        if not sub_path:
            sub_path = "/"
        target_url = f"{AUTH_BACKEND}{sub_path}"
        try:
            resp = requests.request(
                method=request.method,
                url=target_url,
                params=request.query_params,
                data=body,
                headers=headers,
                timeout=5
            )
            response = Response(
                content=resp.content,
                status_code=resp.status_code,
                media_type=resp.headers.get("content-type", "application/json")
            )
            response.headers["X-Gateway"] = "Local-API-Gateway"
            return response
        except requests.exceptions.RequestException as e:
            return Response(
                content=f'{{"error": "Auth-сервис недоступен", "details": "{str(e)}"}}',
                status_code=502,
                media_type="application/json"
            )

    # 2. Проксирование /catalog/ на Catalog-сервис (Round-Robin)
    elif full_path.startswith("/catalog"):
        sub_path = full_path[len("/catalog"):]  # /products, /products/1
        if not sub_path:
            sub_path = "/"

        tried_count = 0
        max_tries = len(CATALOG_BACKENDS)
        last_error = None

        while tried_count < max_tries:
            target_backend = next(catalog_cycle)
            target_url = f"{target_backend}{sub_path}"
            tried_count += 1
            try:
                resp = requests.request(
                    method=request.method,
                    url=target_url,
                    params=request.query_params,
                    data=body,
                    headers=headers,
                    timeout=2
                )
                response = Response(
                    content=resp.content,
                    status_code=resp.status_code,
                    media_type=resp.headers.get("content-type", "application/json")
                )
                response.headers["X-Gateway"] = "Local-API-Gateway"
                if "X-Handled-By" in resp.headers:
                    response.headers["X-Handled-By"] = resp.headers["X-Handled-By"]
                return response
            except requests.exceptions.RequestException as e:
                last_error = str(e)
                continue

        return Response(
            content=f'{{"error": "Все инстансы Catalog недоступны", "details": "{last_error}"}}',
            status_code=502,
            media_type="application/json"
        )

    else:
        return Response(
            content=f'{{"error": "Маршрут не найден в API Gateway: {full_path}"}}',
            status_code=404,
            media_type="application/json"
        )


if __name__ == "__main__":
    print("Запуск локального API Gateway на http://127.0.0.1:8080...")
    uvicorn.run(app, host="127.0.0.1", port=8080)
