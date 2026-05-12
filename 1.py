import asyncio
import httpx


GATEWAY_URL = "http://localhost:8080/v1/generate"
API_KEY = "dev-test-key-12345"
NUM_REQUESTS = 15


async def send_one(client: httpx.AsyncClient, idx: int) -> None:
    try:
        response = await client.post(
            GATEWAY_URL,
            headers={"Authorization": f"Bearer {API_KEY}"},
            json={
                "model": "qwen3",
                "prompt": f"Скажи одно слово, запрос номер {idx}",
                "max_tokens": 10,
                "temperature": 0.7,
            },
            timeout=60.0,
        )
        print(f"[{idx:02d}] status={response.status_code}")
        if response.status_code != 200:
            print(f"     detail: {response.text[:200]}")
    except Exception as e:
        print(f"[{idx:02d}] exception: {e}")


async def main() -> None:
    async with httpx.AsyncClient() as client:
        # Шлём все запросы параллельно
        tasks = [send_one(client, i) for i in range(NUM_REQUESTS)]
        await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())