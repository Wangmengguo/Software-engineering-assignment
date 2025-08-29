from django.urls import path
from .views_api import deal_hand_api, get_replay_api, metrics_api
from .views import teaching_view
from .views_play import (
    session_start_api,
    hand_start_api,
    hand_state_api,
    hand_act_api,
    session_state_api,
    session_next_api,
)
from .views_suggest import SuggestView
from . import metrics

urlpatterns = [
    path("table/deal", deal_hand_api, name="deal"),
    # Backward-compat route (kept): /api/v1/replay/<hand_id>
    path("replay/<str:hand_id>", get_replay_api, name="replay"),
    # New route aligned with docs: /api/v1/hand/<hand_id>/replay
    path("hand/<str:hand_id>/replay", get_replay_api, name="hand_replay"),
    path("metrics", metrics_api, name="metrics"),
    path("metrics/prometheus", metrics.prometheus_view, name="metrics_prom"),
    path("teaching/hand/<str:hand_id>", teaching_view, name="teaching"),
    path("session/start", session_start_api, name="session_start"),
    path("hand/start", hand_start_api, name="hand_start"),
    path("hand/state/<str:hand_id>", hand_state_api, name="hand_state"),
    path("hand/act/<str:hand_id>", hand_act_api, name="hand_act"),
    path("session/<str:session_id>/state", session_state_api, name="session_state"),
    path("session/next", session_next_api, name="session_next"),
    path("suggest", SuggestView.as_view(), name="suggest"),
]
