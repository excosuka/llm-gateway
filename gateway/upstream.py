import json
import time

import httpx
from pydantic import ValidationError

from gateway.config import UpstreamConfig
from gateway.schemas import (
    FinishReason,
    GenerateRequest,
    GenerateResponse,
    Usage,
)

class UpstreamError(Exception):

    def __init__(self, category: str, detail: str) -> None:
        super().__init__(f"{category}: {detail}")
        self.category = category
        self.detail = detail


class UpstreamClient:
    def __init__(self, upstream: UpstreamConfig) -> None:
        self._upstream = upstream
        self._client = httpx.AsyncClient(
            base_url=upstream.url,
            timeout=httpx.Timeout(connect=10.0, read=upstream.timeout,write=10.0,pool=5.0),
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def generate(
        self,
        request: GenerateRequest,
        request_id: str,
    ) -> GenerateResponse:
        start_time = time.monotonic()

        payload = {
            "model": self._upstream.model_id,
            "messages": [{"role": "user", "content": request.prompt}],
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        if request.stop is not None:
            payload["stop"] = request.stop
        try:
            response = await self._client.post("/v1/chat/completions", json=payload)

        except httpx.TimeoutException  as e:
            raise UpstreamError("timeout", str(e))
        except httpx.ConnectError  as e:
            raise UpstreamError("connect", str(e))
        except httpx.HTTPError  as e:
            raise UpstreamError("http error", str(e))

        if response.status_code != 200:
            raise UpstreamError("upstream_error", f"vLLM returned {response.status_code}: {response.text[:200]}")

        try:
            json_response = response.json()
            message_content = json_response["choices"][0]["message"]["content"]
            reason_of_finish = json_response["choices"][0]["finish_reason"]
            tokens_usage = json_response["usage"]


        except (json.JSONDecodeError, KeyError, IndexError) as e:
            raise UpstreamError("bad_response", f"unexpected response structure: {e}")

        try:
            reason_of_finish = FinishReason(reason_of_finish)
        except ValueError:
            reason_of_finish = FinishReason.STOP

        latency_ms = int((time.monotonic() - start_time) * 1000)

        try:
            return GenerateResponse(
                request_id=request_id,
                model=request.model,
                text=message_content,
                usage=Usage(**tokens_usage),
                finish_reason=reason_of_finish,
                latency_ms=latency_ms,
            )

        except ValidationError as e:
            raise UpstreamError("bad_response", f"validation error: {e}")




_clients: dict[str, UpstreamClient] = {}


def init_upstreams(upstreams: list[UpstreamConfig]) -> None:
    for upstream in upstreams:
        _clients[upstream.name] = UpstreamClient(upstream)


def get_upstream(name: str) -> UpstreamClient:
    client = _clients.get(name)
    if client is None:
        raise KeyError(f"Upstream '{name}' is not configured")
    return client


async def close_all_upstreams() -> None:
    for client in _clients.values():
        await client.close()