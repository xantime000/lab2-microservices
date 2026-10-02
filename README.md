# Лабораторная работа №2: Базовые микросервисы и API Gateway

В проекте полностью реализованы все требования из чек-листа преподавателя:
1. **Функциональные требования (Код сервисов)**: Auth-сервис, Catalog-сервис, Service Discovery (Consul).
2. **Инфраструктура и развертывание (Docker)**: Dockerfile для каждого сервиса, docker-compose.yml, изоляция портов.
3. **API Gateway и Балансировка нагрузки**: Nginx шлюз, маршрутизация /auth/* и /catalog/*, Round-Robin балансировка, отказоустойчивость.

---

## 📋 Таблица соответствия чек-листу преподавателя

| Требование из чек-листа | Как реализовано | Где посмотреть в коде |
|---|---|---|
| **Auth: Регистрация** | Метод `POST /auth/register` сохраняет логин и хеш пароля (in-memory) | `auth_service/app.py` |
| **Auth: Вход (Login)** | Метод `POST /auth/login` сверяет данные и выпускает валидный JWT (HS256) | `auth_service/app.py` |
| **Auth: Защищенный метод** | Метод `GET /auth/me` отклоняет запросы без токена (`401`) и пускает с валидным JWT (`200`) | `auth_service/app.py` |
| **Catalog: CRUD** | Полный набор: `POST`, `GET`, `PUT`, `DELETE` для `/catalog/products` | `catalog_service/app.py` |
| **Catalog: Идентификация инстанса** | В каждом GET-ответе возвращается `"instance_id": INSTANCE_ID` и заголовок `X-Handled-By` | `catalog_service/app.py` |
| **Consul: Авто-регистрация** | Сервис регистрирует себя в Consul при старте через HTTP API с health check | `auth_service/app.py`, `catalog_service/app.py` |
| **Consul: Авто-дерегистрация** | Сервис снимает себя с регистрации в Consul при корректном завершении работы | `auth_service/app.py`, `catalog_service/app.py` |
| **Docker: Dockerfile** | Написаны для `auth_service` и `catalog_service` на базе `python:3.10-slim` | `auth_service/Dockerfile`, `catalog_service/Dockerfile` |
| **Docker: docker-compose.yml** | Вся система (Consul, Auth, Catalog x2, Gateway) поднимается одной командой | `docker-compose.yml` |
| **Docker: Множественные инстансы** | В docker-compose запущены два экземпляра каталога: `catalog-1` и `catalog-2` | `docker-compose.yml` |
| **Gateway: Единая точка входа** | Наружу хоста открыт ТОЛЬКО Gateway (порт 80/8080). Прямые порты микросервисов не проброшены наружу | `docker-compose.yml` |
| **Gateway: Маршрутизация** | Запросы `/auth/*` идут на Auth-сервис, а `/catalog/*` — на Catalog-сервис | `nginx/nginx.conf` |
| **Gateway: Балансировка** | Round-Robin поочередно направляет запросы на `catalog-1` и `catalog-2` | `nginx/nginx.conf` |
| **Gateway: Отказоустойчивость** | Директива `proxy_next_upstream error timeout http_502 http_503;` при `docker stop catalog-1` мгновенно направляет трафик на `catalog-2` без ошибок клиенту | `nginx/nginx.conf` |

---

## 🚀 Как протестировать на Windows БЕЗ Docker

Docker на машине не требуется. Всё работает напрямую через Python:

### Шаг 1: Запуск всех сервисов и локального шлюза (Терминал 1)
```powershell
cd C:\Users\xntm\.gemini\antigravity\scratch\lab2-microservices
python run_local.py
```
*Запустятся: Auth-сервис (порт 5001), Catalog-1 (порт 5002), Catalog-2 (порт 5003) и локальный API Gateway (порт 8080).*

### Шаг 2: Запуск автоматического теста по чек-листу (Терминал 2)
```powershell
cd C:\Users\xntm\.gemini\antigravity\scratch\lab2-microservices
python test_all.py
```
Тест автоматически проверит и выведет:
1. Проверку регистрации и входа с JWT.
2. Проверку отклонения запроса к `/auth/me` без токена (401).
3. Проверку успешного доступа к `/auth/me` с валидным JWT (200).
4. Создание, чтение, изменение и удаление товара в `/catalog/products`.
5. Чередование `instance_id` (`catalog-1` -> `catalog-2` -> `catalog-1`) при запросах к шлюзу.

---

## 🐳 Запуск в Docker (для сдачи преподавателю)

```bash
docker compose up --build
```

- **API Gateway (Nginx):** `http://localhost:80`
- **Consul Web UI:** `http://localhost:8500` (видно регистрацию сервисов и зеленые health checks)
- **Запуск автотеста:**
```bash
python test_all.py http://localhost:80
```
- **Проверка отказоустойчивости:**
Остановите первый инстанс:
```bash
docker stop catalog-1
```
Повторите запросы к `http://localhost:80/catalog/products` — все запросы без единой ошибки продолжат обслуживаться оставшимся `catalog-2`!
