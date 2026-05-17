from fastapi import HTTPException, status, Request

from gateway.config import RoutingConfig
from gateway.upstream import UpstreamClient


class Router:
    """Маппит gateway-имя модели на UpstreamClient."""

    def __init__(self, routing: RoutingConfig, upstreams: dict[str, UpstreamClient]) -> None:
        self._routing = routing
        self._upstreams = upstreams

    def resolve(self, model_name: str) -> UpstreamClient:
        """
        По имени модели из gateway-API возвращает UpstreamClient.
        Бросает HTTPException(400), если модель неизвестна.
        """
        try:
            model_from_routing = self._routing.models[model_name]
        except KeyError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown model: {model_name}",
            )

        try:
            return self._upstreams[model_from_routing]
        except KeyError as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Misconfigured routing: {e}",
            )

def get_router(request: Request) -> Router:
    return request.app.state.router