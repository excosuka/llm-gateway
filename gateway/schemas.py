from enum import Enum

from pydantic import BaseModel, Field


class FinishReason(str, Enum):
    STOP = "stop"
    LENGTH = "length"
    CONTENT_FILTER = "content_filter"

class GenerateRequest(BaseModel):
    model: str = Field(..., description="Имя модели из routing")
    prompt: str = Field(..., min_length=1, description="Текст промпта")
    max_tokens: int = Field(default=200, gt=0, le=4096)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    stop: list[str] | None = Field(default=None)


class Usage(BaseModel):
    prompt_tokens: int = Field(..., ge=0)
    completion_tokens: int = Field(..., ge=0)
    total_tokens: int = Field(..., ge=0)

class GenerateResponse(BaseModel):
    request_id: str = Field(..., description="UUID запроса, генерируется gateway")
    model: str = Field(..., description="Имя модели в формате gateway-API (то что клиент передал в запросе)")
    text: str = Field(...)
    usage: Usage
    finish_reason: FinishReason
    latency_ms: int



class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None