import asyncio
from random import randint
import time
import statistics
import httpx

VLLM_URL = "http://localhost:8000/v1/chat/completions"
MODEL = "Qwen/Qwen2.5-3B-Instruct-AWQ"

SYSTEM_PROMPT = """Ты — опытный технический ассистент с глубокими знаниями в области программирования, архитектуры программного обеспечения и системного дизайна. Твоя роль — помогать инженерам разбираться в сложных технических вопросах, объяснять концепции точно и понятно, и предлагать практические решения реальных задач.

Когда отвечаешь на вопросы, придерживайся следующих принципов:
1. Сначала уточни суть вопроса, если он неоднозначен
2. Структурируй ответ от общего к частному
3. Приводи конкретные примеры из реальной разработки
4. Указывай tradeoffs и ограничения каждого решения
5. Избегай абстрактных формулировок, давай practical advice
6. Если вопрос пересекается с несколькими областями — обозначь это явно
7. Когда речь идёт о выборе технологии, всегда обсуждай альтернативы
8. Предупреждай о типичных ошибках и подводных камнях
9. Используй точную техническую терминологию
10. Если не уверен в ответе — прямо скажи об этом, а не выдумывай

Твой стиль общения — прямой, по делу, без воды. Ты ценишь время инженера, который к тебе обращается, и уважаешь его уровень компетенции. Не упрощай чрезмерно, но и не усложняй там, где это не нужно. Помни: цель не показать свою экспертизу, а решить задачу собеседника. Когда даёшь рекомендации, обосновывай их — не "потому что так принято", а "потому что вот такие конкретные причины". Опирайся на свой опыт работы с production-системами и реальными инженерными задачами. Если видишь что вопрос симптом более глубокой проблемы — обозначь это и предложи смотреть глубже."""

# Набор разнообразных промптов, чтобы избежать одинакового KV-cache
PROMPTS = [
    "Объясни, что такое рекурсия, в трёх предложениях.",
    "Напиши короткий стих про осень.",
    "Какие плюсы и минусы у Python для ML?",
    "Расскажи про принцип работы HTTP.",
    "Что такое транзакция в базе данных?",
    "Опиши процесс компиляции C++ в исполняемый файл.",
    "Чем отличается TCP от UDP?",
    "Как работает индексирование в SQL?",
    "Объясни паттерн Observer на примере.",
    "Что такое garbage collection и зачем он нужен?",
]

# Параметры запроса
MAX_TOKENS = 200
TEMPERATURE = 0.7
NUM_REQUESTS = 50  # сколько запросов в эксперименте


def make_payload(prompt: str) -> dict:
    return {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": MAX_TOKENS,
        "temperature": TEMPERATURE,
    }


async def send_one(client: httpx.AsyncClient, prompt: str) -> dict:
    start = time.perf_counter()
    response = await client.post(VLLM_URL, json=make_payload(prompt), timeout=600.0)
    elapsed = time.perf_counter() - start
    data = response.json()
    completion_tokens = data["usage"]["completion_tokens"]
    return {"latency": elapsed, "completion_tokens": completion_tokens}


async def run_sequential(prompts: list[str]) -> list[dict]:
    """Запросы один за другим, без параллелизма."""
    results = []
    async with httpx.AsyncClient() as client:
        for prompt in prompts:
            result = await send_one(client, prompt)
            results.append(result)
    return results


async def run_concurrent(prompts: list[str]) -> list[dict]:
    """Все запросы стартуют параллельно — vLLM сам их батчит."""
    async with httpx.AsyncClient() as client:
        tasks = [send_one(client, prompt) for prompt in prompts]
        results = await asyncio.gather(*tasks)
    return results


def summarize(name: str, results: list[dict], wall_time: float) -> None:
    latencies = [r["latency"] for r in results]
    total_completion_tokens = sum(r["completion_tokens"] for r in results)
    avg_completion = total_completion_tokens / len(results)

    p50 = statistics.median(latencies)
    p95 = statistics.quantiles(latencies, n=20)[18]
    p99 = statistics.quantiles(latencies, n=100)[98]
    avg = statistics.mean(latencies)

    rps = len(results) / wall_time
    tokens_per_sec = total_completion_tokens / wall_time

    print(f"\n=== {name} ===")
    print(f"Total requests:    {len(results)}")
    print(f"Wall time:         {wall_time:.2f}s")
    print(f"Throughput:        {rps:.2f} req/s")
    print(f"Token throughput:  {tokens_per_sec:.1f} tok/s")
    print(f"Avg completion:    {avg_completion:.1f} tokens")
    print(f"Latency avg:       {avg:.2f}s")
    print(f"Latency p50:       {p50:.2f}s")
    print(f"Latency p95:       {p95:.2f}s")
    print(f"Latency p99:       {p99:.2f}s")

async def main() -> None:
    # Готовим NUM_REQUESTS промптов, циклически из PROMPTS
    prompts = [PROMPTS[i % len(PROMPTS)] for i in range(NUM_REQUESTS)]

    print(f"Warmup...")
    async with httpx.AsyncClient() as client:
        # Прогрев single-request режима
        for _ in range(3):
            await send_one(client, "Скажи привет одним словом.")
        # Прогрев батч-режима — vLLM скомпилирует CUDA-графы под размер батча
        warmup_tasks = [send_one(client, "Скажи привет одним словом.") for _ in range(16)]
        await asyncio.gather(*warmup_tasks)
    print("Warmup done.\n")

    print(f"\nRunning SEQUENTIAL ({NUM_REQUESTS} requests, one at a time)...")
    start = time.perf_counter()
    seq_results = await run_sequential(prompts)
    seq_time = time.perf_counter() - start
    summarize("SEQUENTIAL", seq_results, seq_time)

    print(f"\nRunning CONCURRENT ({NUM_REQUESTS} requests in parallel)...")
    start = time.perf_counter()
    conc_results = await run_concurrent(prompts)
    conc_time = time.perf_counter() - start
    summarize("CONCURRENT", conc_results, conc_time)

    print(f"\n=== COMPARISON ===")
    print(f"Throughput speedup: {(len(conc_results)/conc_time) / (len(seq_results)/seq_time):.2f}x")


if __name__ == "__main__":
    asyncio.run(main())