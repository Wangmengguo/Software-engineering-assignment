# apps/web_django/api/metrics.py
try:
    from prometheus_client import Histogram, Counter
    SUGGEST_LATENCY = Histogram("suggest_latency_seconds", "Suggest latency", ["policy", "street"])
    SUGGEST_ERRORS  = Counter("suggest_errors_total",   "Suggest errors",   ["type", "street"])
    SUGGEST_ACTION  = Counter("suggest_action_total",   "Suggested actions", ["policy", "street", "action"])

    def observe_latency(policy: str, street: str, seconds: float):
        SUGGEST_LATENCY.labels(policy or "unknown", street or "unknown").observe(seconds)

    def inc_error(err_type: str, street: str = None):
        SUGGEST_ERRORS.labels(err_type or "unknown", street or "unknown").inc()

    def inc_action(policy: str, action: str, street: str = None):
        SUGGEST_ACTION.labels(policy or "unknown", street or "unknown", action or "unknown").inc()

    # 扩展指标：游戏流程监控
    SESSION_STARTS = Counter("session_starts_total", "Session creation count", ["status"])
    HAND_STARTS = Counter("hand_starts_total", "Hand creation count", ["status"])
    HAND_ACTIONS = Counter("hand_actions_total", "Hand actions count", ["action", "street"])

    def inc_session_start(status: str = "success"):
        SESSION_STARTS.labels(status).inc()

    def inc_hand_start(status: str = "success"):
        HAND_STARTS.labels(status).inc()

    def inc_hand_action(action: str, street: str = None):
        HAND_ACTIONS.labels(action or "unknown", street or "unknown").inc()

except Exception:  # 无 Prometheus 时降级为 no-op
    def observe_latency(policy: str, street: str, seconds: float):
        pass
    def inc_error(err_type: str, street: str = None):
        pass
    def inc_action(policy: str, action: str, street: str = None):
        pass

    # 扩展指标的no-op版本
    def inc_session_start(status: str = "success"):
        pass
    def inc_hand_start(status: str = "success"):
        pass
    def inc_hand_action(action: str, street: str = None):
        pass