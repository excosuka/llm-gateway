import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiofiles


logger = logging.getLogger(__name__)


class RequestLogger:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    async def log_request(
            self,
            *,
            request_id: str,
            client: str,
            model: str,
            prompt: str,
            response_text: str | None,
            prompt_text: str | None,
            prompt_tokens: int | None,
            completion_tokens: int | None,
            latency_ms: int | None,
            status_code: int,
            finish_reason: str | None,
            error_category: str | None,
            error_detail: str | None,
    ) -> None:
        record: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": request_id,
            "client": client,
            "model": model,
            "prompt": prompt,
            "response_text": response_text,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "latency_ms": latency_ms,
            "status_code": status_code,
            "finish_reason": finish_reason,
            "error_category": error_category,
            "error_detail": error_detail,
        }
        line = json.dumps(record, ensure_ascii=False) + "\n"

        try:
            async with aiofiles.open(self._path, mode="a", encoding="utf-8") as f:
                await f.write(line)
        except OSError as e:
            # Не валим запрос если запись лога упала. Просто варним в operational-лог.
            logger.warning("Failed to write request log: %s", e)



_request_logger: RequestLogger | None = None


def init_request_logger(path: str | Path) -> None:
    global _request_logger
    _request_logger = RequestLogger(path)


def get_request_logger() -> RequestLogger:
    if _request_logger is None:
        raise RuntimeError("RequestLogger is not initialized")
    return _request_logger