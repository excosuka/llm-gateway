

from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from gateway.config import ApiKeyConfig

bearer_scheme = HTTPBearer(auto_error=False)

class AuthService:
    def __init__(self, api_keys: list[ApiKeyConfig]) -> None:
        self._keys = {config.key:config for config in api_keys}

    def authenticate(self, token: str) ->ApiKeyConfig:
        config = self._keys.get(token)
        if config is None:
            raise HTTPException(status_code=401, detail="Invalid Api-Key")
        return config



_auth_service: AuthService | None = None


def init_auth(service: AuthService) -> None:
    global _auth_service
    _auth_service = service


def get_authenticated_key(
        credentials: HTTPAuthorizationCredentials  | None = Depends(bearer_scheme),
) -> ApiKeyConfig:
    """FastAPI dependency. Возвращает ApiKeyConfig для текущего запроса."""
    if _auth_service is None:
        raise RuntimeError("AuthService is not initialized")
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Missing Authorization header",
        )
    return _auth_service.authenticate(credentials.credentials)