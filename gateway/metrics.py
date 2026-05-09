from prometheus_client import Counter, Gauge, Histogram


REQUESTS_TOTAL = Counter(
    "gateway_requests_total",
    "Total number of requests handled by the gateway",
    labelnames=["status", "model", "client"],
)

REQUEST_DURATION = Histogram(
    "gateway_request_duration_seconds",
    "Request handling latency at the gateway boundary",
    labelnames=["model"],
    # Бакеты в секундах: тонкая гранулярность на быстрых, крупная на медленных
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0),
)

TOKENS_TOTAL = Counter(
    "gateway_tokens_total",
    "Total number of tokens processed",
    labelnames=["kind", "model"],  # kind: prompt | completion
)

UPSTREAM_ERRORS_TOTAL = Counter(
    "gateway_upstream_errors_total",
    "Number of upstream errors by category",
    labelnames=["category"],
)


IN_FLIGHT = Gauge(
    "gateway_in_flight_requests",
    "Number of requests currently being processed",
)