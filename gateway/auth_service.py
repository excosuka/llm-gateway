

from fastapi import HTTPException, Depends, Request
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


def get_auth_service(request: Request) -> AuthService:
    return request.app.state.auth_service


def get_authenticated_key(
        credentials: HTTPAuthorizationCredentials  | None = Depends(bearer_scheme),
        auth_service: AuthService = Depends(get_auth_service)
) -> ApiKeyConfig:

    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Missing Authorization header",
        )

    return auth_service.authenticate(credentials.credentials)

