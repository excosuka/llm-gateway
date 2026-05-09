from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ConfigDict


class ServerConfig(BaseModel):
    host: str
    port: int

class UpstreamConfig(BaseModel):
    name: str
    url: str
    model_id: str
    timeout: float


class RoutingConfig(BaseModel):
    default: str
    models: dict[str, str]


class RateLimitConfig(BaseModel):
    tokens_per_second: float
    bucket_size: int


class ApiKeyConfig(BaseModel):
    key: str
    name: str
    rate_limit: RateLimitConfig


class LoggingConfig(BaseModel):
    level: str
    requests_log_path: str


class AppConfig(BaseModel):
    server: ServerConfig
    upstreams: list[UpstreamConfig]
    routing: RoutingConfig
    api_keys: list[ApiKeyConfig]
    logging: LoggingConfig


def load_config(path: str | Path) -> AppConfig:
    try:
        with open(path, "r") as f:
            config = yaml.safe_load(f)
        config = AppConfig(**config)
        return config
    except FileNotFoundError:
        raise FileNotFoundError

