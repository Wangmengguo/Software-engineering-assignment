# apps/web_django/api/views_suggest.py
from __future__ import annotations
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, serializers
from poker_core.suggest.service import build_suggestion
from poker_core.domain.actions import legal_actions_struct
from drf_spectacular.utils import extend_schema, OpenApiResponse, inline_serializer
import logging
from .state import HANDS
import hashlib, json

logger = logging.getLogger(__name__)

class SuggestReqSerializer(serializers.Serializer):
    hand_id = serializers.CharField()
    actor = serializers.IntegerField(min_value=0, max_value=1)

class SuggestedSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["fold","check","call","bet","raise","allin"])
    amount = serializers.IntegerField(required=False, min_value=1)

class RationaleItemSerializer(serializers.Serializer):
    code = serializers.CharField()
    msg = serializers.CharField()
    data = serializers.JSONField(required=False)

class SuggestRespSerializer(serializers.Serializer):
    hand_id = serializers.CharField()
    actor = serializers.IntegerField(min_value=0, max_value=1)
    suggested = SuggestedSerializer()
    rationale = RationaleItemSerializer(many=True)
    policy = serializers.CharField()

class SuggestView(APIView):
    @extend_schema(
        request=SuggestReqSerializer,
        responses={
            200: OpenApiResponse(response=SuggestRespSerializer, description="OK"),
            404: inline_serializer(name="SuggestErr404", fields={"detail": serializers.CharField()}),
            409: inline_serializer(name="SuggestErr409", fields={"detail": serializers.CharField()}),
            422: inline_serializer(name="SuggestErr422", fields={"detail": serializers.CharField()}),
        },
        tags=["suggest"],
        summary="Return a minimal legal suggestion for the given hand/actor",
    )
    def post(self, request, *args, **kwargs):
        ser = SuggestReqSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        hand_id = ser.validated_data["hand_id"]
        actor = ser.validated_data["actor"]

        entry = HANDS.get(hand_id) or {}
        gs = entry.get("gs")
        if gs is None:
            return Response({"detail": "hand not found"}, status=status.HTTP_404_NOT_FOUND)

        # 以 street==complete 判断完结
        if getattr(gs, "street", None) == "complete":
            return Response({"detail": "hand already ended"}, status=status.HTTP_409_CONFLICT)

        try:
            # 观测：记录合法动作摘要（便于复现）
            try:
                la_struct = legal_actions_struct(gs)
                la_compact = [
                    {k: v for k, v in {
                        "a": a.action,
                        "min": a.min,
                        "max": a.max,
                        "tc": a.to_call,
                    }.items() if v is not None}
                    for a in la_struct
                ]
                la_json = json.dumps(la_compact, separators=(",", ":"), ensure_ascii=False)
                la_hash = hashlib.sha1(la_json.encode("utf-8")).hexdigest()[:8]
            except Exception:
                la_hash = None
                la_json = None

            resp = build_suggestion(gs, actor)
            # 结构化日志
            logger.info(
                "suggest",
                extra={
                    "hand_id": hand_id,
                    "actor": actor,
                    "policy": resp.get("policy"),
                    "action": resp.get("suggested", {}).get("action"),
                    "amount": resp.get("suggested", {}).get("amount"),
                    "la_hash": la_hash,
                    # 警惕日志体积，必要时去掉 la_compact
                    # "la_compact": la_json,
                },
            )
            return Response(resp, status=status.HTTP_200_OK)
        except PermissionError:
            return Response({"detail": "not actor's turn"}, status=status.HTTP_409_CONFLICT)
        except ValueError as e:
            return Response({"detail": f"suggest failed: {e}"}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
