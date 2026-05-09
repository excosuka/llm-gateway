from fastapi import HTTPException, status

from gateway.config import RoutingConfig
from gateway.upstream import UpstreamClient, get_upstream


class Router:
    """Маппит gateway-имя модели на UpstreamClient."""

    def __init__(self, routing: RoutingConfig) -> None:
        self._routing = routing

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
            return get_upstream(model_from_routing)
        except KeyError as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Misconfigured routing: {e}",
            )


_router: Router | None = None


def init_router(routing: RoutingConfig) -> None:
    global _router
    _router = Router(routing)


def get_router() -> Router:
    if _router is None:
        raise RuntimeError("Router is not initialized")
    return _router