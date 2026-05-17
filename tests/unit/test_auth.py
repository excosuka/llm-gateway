import pytest
from fastapi import HTTPException

from gateway import auth_service
from gateway.auth_service import AuthService
from gateway.config import ApiKeyConfig, RateLimitConfig


def make_api_key(key, name):
    return ApiKeyConfig(key=key, name=name, rate_limit=RateLimitConfig(tokens_per_second=10, bucket_size=100))

def test_authenticate_distinguishes_between_multiple_keys():
    test_api_key_config_1 = make_api_key("test_api_key_1", "doctor")
    test_api_key_config_2 = make_api_key("test_api_key_2", "policeman")

    test_auth_service = AuthService([test_api_key_config_1, test_api_key_config_2])

    result_1 = test_auth_service.authenticate("test_api_key_1")
    result_2 = test_auth_service.authenticate("test_api_key_2")

    assert result_1.name == "doctor"
    assert result_2.name == "policeman"


def test_authenticate_is_case_sensitive():
    test_api_key_config = make_api_key("SECRET", "doctor")

    test_auth_service = AuthService([test_api_key_config])

    with pytest.raises(HTTPException) as exc_info:
        test_auth_service.authenticate("secret")

    assert exc_info.value.status_code == 401


def test_authenticate_with_empty_keys_always_fails():
    test_auth_service = AuthService([])

    with pytest.raises(HTTPException) as exc_info:
        test_auth_service.authenticate("anything")

    assert exc_info.value.status_code == 401


def test_authenticate_with_invalid_key_raises_401():
    test_api_key_config = make_api_key("test_api_key_1", "doctor")

    test_auth_service = AuthService([test_api_key_config])

    with pytest.raises(HTTPException) as exc_info:
        test_auth_service.authenticate("wrong_key")

    assert exc_info.value.status_code == 401


def test_authenticate_with_valid_key_returns_config():
    test_api_key_config = make_api_key("test_api_key", "doctor")
    test_auth_service = AuthService([test_api_key_config])

    result = test_auth_service.authenticate("test_api_key")

    assert result.name == "doctor"