# LLM Gateway

FastAPI-шлюз перед vLLM с аутентификацией, rate limiting, роутингом моделей и корректной обработкой ошибок upstream.

## Зачем это нужно

Голый vLLM выставляет OpenAI-совместимое API в сеть. Для прототипов это нормально, но в проде нужен слой, который решает задачи, не входящие в зону ответственности inference-движка.

**Аутентификация и контроль доступа.** vLLM принимает запросы от любого, кто может достучаться до порта. Шлюз проверяет `Authorization: Bearer <key>` против списка API-ключей из конфига до того, как запрос попадёт на GPU.

**Rate limiting на каждого клиента.** Без лимитов один клиент может загрузить GPU и заморить остальных. Шлюз реализует token bucket на API-ключ с настраиваемым rate'ом и burst size.

**Роутинг моделей.** Клиент не должен знать о физическом имени модели (`Qwen/Qwen2.5-3B-Instruct-AWQ`). Шлюз маппит дружественные имена (`qwen3`, `fast`) на конкретные upstream-инстансы. Это позволяет менять модель без поломки клиентов.

**Корректная HTTP-семантика для proxy-ошибок.** Когда vLLM таймаутит, отказывает в соединении или возвращает мусор, клиент должен видеть осмысленные коды (504, 503, 502), а не общий 500. Шлюз транслирует upstream-ошибки в правильные HTTP-ответы.

**Точка для observability.** У каждого запроса есть UUID, latency меряется на уровне шлюза. Структурированные логи и метрики живут именно на этой границе (запланировано в roadmap).

## Quick start

### Требования

- Python 3.11+
- Docker с NVIDIA Container Toolkit
- NVIDIA GPU с минимум 8 GB VRAM
- Hugging Face аккаунт с access-токеном

### Настройка секретов

Создай файл `.env` в корне проекта (он в `.gitignore`):

```
HF_TOKEN=hf_твой_токен_здесь
```

Или экспортируй переменную в shell перед запуском.

### Запуск vLLM (upstream)

```bash
docker run --rm -it --gpus all \
  -v D:/hf-cache:/root/.cache/huggingface \
  -p 8000:8000 \
  --ipc=host \
  -e HUGGING_FACE_HUB_TOKEN=$HF_TOKEN \
  vllm/vllm-openai:latest \
  --model Qwen/Qwen2.5-3B-Instruct-AWQ \
  --quantization awq \
  --max-model-len 4096 \
  --gpu-memory-utilization 0.85
```

Дождись в логах строки `Uvicorn running on http://0.0.0.0:8000` перед запуском шлюза.

### Запуск шлюза

```bash
pip install -r requirements.txt
uvicorn gateway.main:app --host 0.0.0.0 --port 8080 --reload
```

Шлюз читает конфигурацию из `config.yaml` в рабочей директории.

### Тестовый запрос

PowerShell:

```powershell
$body = @{
    model = "qwen3"
    prompt = "Объясни что такое Docker в трёх предложениях."
    max_tokens = 200
    temperature = 0.7
} | ConvertTo-Json

Invoke-RestMethod -Uri http://localhost:8080/v1/generate `
    -Method Post `
    -Headers @{
        "Authorization" = "Bearer dev-test-key-12345"
        "Content-Type" = "application/json"
    } `
    -Body $body
```

Bash:

```bash
curl -X POST http://localhost:8080/v1/generate \
  -H "Authorization: Bearer dev-test-key-12345" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3",
    "prompt": "Объясни что такое Docker в трёх предложениях.",
    "max_tokens": 200,
    "temperature": 0.7
  }'
```

В ответ придёт JSON с полями `request_id`, `text`, `usage`, `finish_reason` и `latency_ms`.

Интерактивные API-доки доступны на http://localhost:8080/docs (автогенерация FastAPI).

## Архитектура

```
                  ┌─────────────────────────────────────────┐
                  │  FastAPI Gateway (порт 8080)            │
                  │                                         │
   Клиент ──────► │  Auth ─► RateLimit ─► Router ─► Upstream│ ──► vLLM (порт 8000)
                  │                                         │
                  │  /health, /docs                         │
                  └─────────────────────────────────────────┘
```

Каждый запрос проходит через цепочку FastAPI-зависимостей перед попаданием в upstream:

- **`auth.py`** — проверяет заголовок `Authorization: Bearer <key>` против API-ключей из конфига. Возвращает соответствующий `ApiKeyConfig` или бросает 401.
- **`ratelimit.py`** — token bucket, in-memory, на каждый API-ключ. У каждого ключа свои `tokens_per_second` и `bucket_size`. Бросает 429 при превышении.
- **`router.py`** — маппит gateway-имя модели (например, `qwen3`) на конкретный upstream-инстанс. Бросает 400 на неизвестные модели.
- **`upstream.py`** — async httpx-клиент к OpenAI-совместимому эндпоинту vLLM. Переводит между gateway- и OpenAI-форматами. Категоризирует ошибки (timeout, connection, upstream_error, bad_response) и поднимает `UpstreamError`, который шлюз маппит в правильный HTTP-код (504, 503, 502).
- **`schemas.py`** — Pydantic-модели для собственного API шлюза (`/v1/generate`). Независимы от OpenAI-схемы.
- **`config.py`** — загружает и валидирует `config.yaml` через Pydantic при старте.
- **`main.py`** — FastAPI-приложение, lifespan-управление инициализацией, exception handlers.

## Конфигурация

Вся конфигурация в `config.yaml`. Основные секции:

- `server` — host и port шлюза.
- `upstreams` — список vLLM-инстансов. Каждый описан полями `name`, `url`, `hf_model_id` (реальное имя модели на HF), `timeout`.
- `routing` — маппинг дружественных имён моделей на upstream-имена. Поле `default` зарезервировано на будущее.
- `api_keys` — список API-ключей с индивидуальными rate limit-настройками.
- `logging` — уровень логов и путь к request log'у.

Рабочий пример с дефолтами лежит в `config.yaml`.

## Ограничения

Это MVP. Известные пробелы:

- **In-memory rate limiter.** Состояние живёт внутри процесса, поэтому работает только при single-worker деплое. Запуск с `uvicorn --workers N` даст каждому воркеру своё ведро и фактически умножит лимит на N. Стандартное решение — Redis-backed limiter.
- **API-ключи в открытом виде в YAML.** Подходит для локальной разработки, не для прода. В реальных деплоях используют secrets manager (Vault, AWS Secrets Manager) или хешированные ключи с ротацией.
- **Нет streaming-ответов.** Сейчас поддерживаются только полные ответы. Streaming (SSE / chunked transfer) пока не реализован.
- **Нет Prometheus-метрик.** Latency, RPS, error rate и token throughput не экспонируются для scrape'инга. В плане.
- **Нет структурированного логирования запросов.** Логи идут в stdout в plain text. Сохранение полных промптов/ответов в JSONL — в плане.
- **Нет тестов.** Это следующий очевидный пробел. Код спроектирован тестируемым (чёткие границы модулей, инжекция через FastAPI Depends), но тестового набора пока нет.
- **Нет retry на upstream-ошибки.** Транзиентный сбой vLLM сейчас уходит сразу клиенту. Добавление bounded retries с exponential backoff несложное, но пока не сделано.
- **Один upstream на модель.** Нет балансировки между несколькими vLLM-репликами. Архитектура это позволяет (реестр upstream'ов — `dict`), но логика роутинга выбирает единственный upstream без стратегии балансировки.

## Roadmap

В порядке приоритета:

1. Prometheus-метрики на `/metrics` — request rate, гистограммы latency, счётчики ошибок по категориям, токены.
2. Структурированное логирование — JSONL-логи запросов/ответов с `request_id` для корреляции, отдельно от operational-логов.
3. Test suite — unit-тесты для `auth`, `ratelimit`, `router`; интеграционные тесты против mock vLLM.
4. Streaming-ответы для длинных генераций.
5. Bounded retries на транзиентные upstream-ошибки.
6. Redis-backed rate limiter для multi-worker деплоя.
7. Кеширование ответов на одинаковые запросы (опционально, зависит от сценария).

## Стек

- FastAPI + Uvicorn (асинхронный веб-фреймворк)
- httpx (асинхронный HTTP-клиент)
- Pydantic v2 (валидация)
- PyYAML (конфиг)
- vLLM (inference-движок, запускается отдельно)