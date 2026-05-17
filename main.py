import json
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from gateway.auth_service import AuthService
from gateway.config import ApiKeyConfig, load_config
from gateway.metrics import IN_FLIGHT, REQUESTS_TOTAL, REQUEST_DURATION, TOKENS_TOTAL, UPSTREAM_ERRORS_TOTAL
from gateway.rate_limiter import RateLimiter, enforce_rate_limit
from gateway.request_log import get_request_logger, RequestLogger

from gateway.router import get_router, Router
from gateway.schemas import GenerateRequest, GenerateResponse
from gateway.upstream import (
    UpstreamError, build_upstreams,
)


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Жизненный цикл: инициализация при старте, очистка при остановке."""
    config = load_config("config.yaml")

    logging.basicConfig(
        level=config.logging.level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info(
        "Gateway started: %d upstreams, %d API keys",
        len(config.upstreams),
        len(config.api_keys),
    )

    # Инициализация singleton'ов
    app.state.auth_service = AuthService(config.api_keys)
    app.state.rate_limiter = RateLimiter()
    app.state.upstreams = build_upstreams(config.upstreams)
    app.state.router = Router(config.routing, app.state.upstreams)
    app.state.request_logger = RequestLogger(config.logging.requests_log_path)



    yield

    # Shutdown
    logger.info("Shutting down...")

    for client in app.state.upstreams.values():
        await client.close()


    logger.info("Goodbye.")


app = FastAPI(
    title="LLM Gateway",
    version="0.1.0",
    lifespan=lifespan,
)


# --- Exception handlers ---

UPSTREAM_ERROR_STATUS_MAP = {
    "TIMEOUT": 504,
    "CONNECTION": 503,
    "UPSTREAM_ERROR": 502,
    "BAD_RESPONSE": 502,
    "HTTP_ERROR": 502
}


@app.exception_handler(UpstreamError)
async def upstream_error_handler(request: Request, exc: UpstreamError) -> JSONResponse:
    UPSTREAM_ERRORS_TOTAL.labels(category=exc.category.value).inc()

    status_code = UPSTREAM_ERROR_STATUS_MAP.get(exc.category.value, 500)
    logger.warning("Upstream error [%s]: %s", exc.category.value, exc.detail)


    model = getattr(request.state, "model", "unknown")
    client = getattr(request.state, "client", "unknown")

    await request.app.state.request_logger.log_request(
        request_id=request.state.request_id,  # у нас здесь нет оригинального request_id
        client=client,
        model=model,
        prompt=request.state.prompt,
        response_text=None,
        prompt_tokens=None,
        completion_tokens=None,
        latency_ms=None,
        status_code=status_code,
        finish_reason=None,
        error_category=exc.category.value,
        error_detail=exc.detail,
    )

    return JSONResponse(
        status_code=status_code,
        content={"error": exc.category.value, "detail": exc.detail},
    )


# --- Routes ---

@app.get("/health")
async def health() -> dict[str, str]:
    """Healthcheck для k8s/docker. Всегда 200 пока процесс живой."""
    return {"status": "ok"}



@app.get("/metrics")
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):

    request.state.prompt = None
    request.state.request_id = str(uuid.uuid4())
    if request.url.path in ("/metrics", "/health"):
        return await call_next(request)

    IN_FLIGHT.inc()
    start = time.monotonic()

    if request.url.path == "/v1/generate":
        request_body = await request.body()
        try:
            request_body = json.loads(request_body)
            request.state.prompt = request_body["prompt"]
        except Exception:
            logger.warning("Failed to parse request body")




    try:

        response = await call_next(request)
        status = str(response.status_code)
    except Exception:

        status = "500"
        raise
    finally:
        duration = time.monotonic() - start
        IN_FLIGHT.dec()

        # После handler'а читаем что он туда положил
        model = getattr(request.state, "model", "unknown")
        client = getattr(request.state, "client", "unknown")

        REQUEST_DURATION.labels(model=model).observe(duration)
        REQUESTS_TOTAL.labels(status=status, model=model, client=client).inc()

    return response


@app.post("/v1/generate", response_model=GenerateResponse)
async def generate(
        request: GenerateRequest,
        http_request: Request,
        api_key: ApiKeyConfig = Depends(enforce_rate_limit),
        router: Router = Depends(get_router),
        logger: RequestLogger = Depends(get_request_logger),
) -> GenerateResponse:
    http_request.state.model = request.model
    http_request.state.client = api_key.name
    request_id = http_request.state.request_id

    upstream = router.resolve(request.model)

    response = await upstream.generate(request, request_id=request_id)

    TOKENS_TOTAL.labels(kind="prompt", model=request.model).inc(response.usage.prompt_tokens)
    TOKENS_TOTAL.labels(kind="completion", model=request.model).inc(response.usage.completion_tokens)

    await logger.log_request(
        request_id=request_id,
        client=api_key.name,
        model=request.model,
        prompt=request.prompt,
        response_text=response.text,
        prompt_tokens=response.usage.prompt_tokens,
        completion_tokens=response.usage.completion_tokens,
        latency_ms=response.latency_ms,
        status_code=200,
        finish_reason=response.finish_reason.value,
        error_category=None,
        error_detail=None,
    )



    return response