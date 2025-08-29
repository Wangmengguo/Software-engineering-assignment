"""
API 视图：游戏流程控制
"""

from __future__ import annotations
import uuid
from typing import Optional
import time
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status, serializers
from drf_spectacular.utils import extend_schema, inline_serializer
from .models import Replay, Session
from .state import HANDS, snapshot_state, METRICS
from django.shortcuts import get_object_or_404
from . import metrics
from poker_core.session_types import SessionView
from poker_core.session_flow import next_hand

# 领域函数（按你项目的实际导入路径调整）
from poker_core.state_hu import (
    start_hand as _start_hand,
    legal_actions as _legal_actions,
    apply_action as _apply_action,
    settle_if_needed as _settle_if_needed,
    start_hand_with_carry as _start_hand_with_carry,
)

# 从 events 中提取 outcome 信息
def _extract_outcome_from_events(gs) -> dict | None:
    # 从最后往前找 showdown 事件
    for e in reversed(getattr(gs, "events", []) or []):
        if e.get("t") == "showdown":
            return {"winner": e.get("winner"), "best5": e.get("best5")}
    # 允许弃牌结束：返回 winner、best5=None
    for e in reversed(getattr(gs, "events", []) or []):
        if e.get("t") == "win_fold":
            return {"winner": e.get("who"), "best5": None}
    return None

# ---------- 1) POST /session/start ----------
@extend_schema(
    request=inline_serializer(name="StartSessionReq", fields={
        "init_stack": serializers.IntegerField(required=False, default=200, min_value=1),
        "sb": serializers.IntegerField(required=False, default=1, min_value=1),
        "bb": serializers.IntegerField(required=False, default=2, min_value=2),
    }),
    responses={200: inline_serializer(name="StartSessionResp", fields={
        "session_id": serializers.CharField(),
        "button": serializers.IntegerField(),
        "stacks": serializers.ListField(child=serializers.IntegerField()),
        "config": serializers.JSONField(),
    })}
)
@api_view(["POST"])
def session_start_api(request):
    import time
    start_time = time.time()
    t0 = time.perf_counter()
    route = "session/start"
    method = "POST"
    status_label = "200"

    try:
        init_stack = int(request.data.get("init_stack", 200))
        sb = int(request.data.get("sb", 1))
        bb = int(request.data.get("bb", 2))

        session_id = str(uuid.uuid4())
        s = Session.objects.create(
            session_id=session_id,
            config={"init_stack": init_stack, "sb": sb, "bb": bb},
            stacks=[init_stack, init_stack],
            button=0,
            hand_counter=1,
            status="running",
        )

        # 记录会话创建成功
        METRICS["deals_total"] += 1  # 复用现有指标
        metrics.inc_session_start("success")  # 使用新的监控指标

        duration = time.time() - start_time
        METRICS["last_latency_ms"] = int(duration * 1000)

        return Response({"session_id": session_id, "button": s.button, "stacks": s.stacks, "config": s.config})

    except Exception as e:
        # 记录错误
        METRICS["error_total"] += 1
        metrics.inc_session_start("failed")  # 记录失败状态
        metrics.inc_error("session_creation_failed", street="unknown")
        status_label = "500"
        try:
            metrics.inc_api_error(route, "exception")
        except Exception:
            pass

        import logging
        logging.error(f"Session creation failed: {e}")
        return Response({"detail": f"Session creation failed: {str(e)}"}, status=500)
    finally:
        try:
            metrics.observe_request(route, method, status_label, time.perf_counter() - t0)
        except Exception:
            pass


# ---------- 2) POST /hand/start ----------
@extend_schema(
    request=inline_serializer(name="StartHandReq", fields={
        "session_id": serializers.CharField(),
        "seed": serializers.IntegerField(required=False, allow_null=True),
        "button": serializers.IntegerField(required=False, allow_null=True),
    }),
    responses={200: inline_serializer(name="StartHandResp", fields={
        "hand_id": serializers.CharField(),
        "state": serializers.JSONField(),
        "legal_actions": serializers.ListField(child=serializers.CharField()),
    })}
)
@api_view(["POST"])
def hand_start_api(request):
    t0 = time.perf_counter()
    route = "hand/start"
    method = "POST"
    session_id = request.data.get("session_id")
    s = get_object_or_404(Session, session_id=session_id)
    if s.status != "running":
        try:
            metrics.observe_request(route, method, "409", time.perf_counter() - t0)
        except Exception:
            pass
        return Response({"detail": "session not running"}, status=409)
    cfg = s.config
    seed: Optional[int] = request.data.get("seed")
    button = request.data.get("button", s.button)
    hand_id = str(uuid.uuid4())

    gs  = _start_hand(cfg, session_id=session_id, hand_id=hand_id, button=int(button), seed=seed)

    HANDS[hand_id] = {"gs": gs, "session_id": session_id, "seed": seed, "cfg": cfg}
    # 下一手按钮建议轮转（这里不直接改，交给结算后更新；先返回当前）
    st = snapshot_state(gs)
    la = list(_legal_actions(gs))
    try:
        resp = Response({"hand_id": hand_id, "state": st, "legal_actions": la})
        return resp
    finally:
        try:
            metrics.observe_request(route, method, "200", time.perf_counter() - t0)
        except Exception:
            pass


# ---------- 3) GET /hand/{hand_id}/state ----------
@extend_schema(
    responses={200: inline_serializer(name="HandStateResp", fields={
        "hand_id": serializers.CharField(),
        "state": serializers.JSONField(),
        "legal_actions": serializers.ListField(child=serializers.CharField()),
    })}
)
@api_view(["GET"])
def hand_state_api(request, hand_id: str):
    t0 = time.perf_counter()
    route = "hand/state"
    method = "GET"
    if hand_id not in HANDS:
        try:
            metrics.observe_request(route, method, "404", time.perf_counter() - t0)
        except Exception:
            pass
        return Response({"detail": "hand not found"}, status=404)
    gs = HANDS[hand_id]["gs"]
    try:
        return Response({"hand_id": hand_id, "state": snapshot_state(gs), "legal_actions": list(_legal_actions(gs))})
    finally:
        try:
            metrics.observe_request(route, method, "200", time.perf_counter() - t0)
        except Exception:
            pass


# ---------- 4) POST /hand/{hand_id}/act ----------
OutcomeSchema = inline_serializer(
    name="Outcome",
    fields={
        "winner": serializers.IntegerField(allow_null=True),
        "best5": serializers.ListField(
            child=serializers.ListField(child=serializers.CharField()),
            allow_null=True
        )
    }
)

@extend_schema(
    request=inline_serializer(name="ActReq", fields={
        "action": serializers.ChoiceField(choices=["check","call","bet","raise","fold","allin"]),
        "amount": serializers.IntegerField(required=False, allow_null=True, min_value=1),
    }),
    responses={200: inline_serializer(name="ActResp", fields={
        "hand_id": serializers.CharField(),
        "state": serializers.JSONField(),
        "legal_actions": serializers.ListField(child=serializers.CharField()),
        "hand_over": serializers.BooleanField(),
        "outcome": OutcomeSchema,
    })}
)
@api_view(["POST"])
def hand_act_api(request, hand_id: str):
    t0 = time.perf_counter()
    route = "hand/act"
    method = "POST"
    if hand_id not in HANDS:
        try:
            metrics.observe_request(route, method, "404", time.perf_counter() - t0)
        except Exception:
            pass
        return Response({"detail": "hand not found"}, status=404)
    gs = HANDS[hand_id]["gs"]

    action = request.data.get("action")
    amount = request.data.get("amount", None)
    try:
        gs = _apply_action(gs, action, amount)
    except ValueError as e:
        try:
            metrics.observe_request(route, method, "400", time.perf_counter() - t0)
            metrics.inc_api_error(route, "validation")
        except Exception:
            pass
        return Response({"detail": str(e)}, status=400)

    # 可能推进到下一街 / 结算
    gs = _settle_if_needed(gs)
    HANDS[hand_id]["gs"] = gs

    # 判断是否结束（按你的实现是 'complete' 或标志位）
    street = getattr(gs, "street", None) or (getattr(gs, "state", {}) or {}).get("street")
    hand_over = (street in {"complete", "showdown_complete"} or getattr(gs, "is_over", False))

    payload = {
        "hand_id": hand_id,
        "state": snapshot_state(gs),
        "legal_actions": list(_legal_actions(gs)) if not hand_over else [],
        "hand_over": hand_over,
    }

    if hand_over:
        outcome = _extract_outcome_from_events(gs)
        if outcome:
            payload["outcome"] = outcome  # ← API 直带最小结果
        
        # ← 最小回放入库：含 winner/best5
        try:
            session_id = HANDS[hand_id]["session_id"]
            seed = HANDS[hand_id]["seed"]
            # 统一的replay数据结构
            from datetime import datetime, timezone
            from poker_core.version import ENGINE_COMMIT, SCHEMA_VERSION
            from poker_core.analysis import annotate_player_hand
            
            # 获取玩家数据和注释
            players_data = []
            annotations_data = []
            if hasattr(gs, 'players'):
                for i, player in enumerate(gs.players):
                    player_info = {
                        "pos": i,
                        "hole": player.hole,
                        "stack": player.stack,
                        "invested": player.invested_street,
                        "folded": player.folded,
                        "all_in": player.all_in,
                    }
                    players_data.append(player_info)
                    
                    # 生成教学注释
                    if player.hole and len(player.hole) == 2:
                        annotation = annotate_player_hand(player.hole)
                        annotations_data.append(annotation)
                    else:
                        annotations_data.append({"info": {}, "notes": []})
            
            # 生成基础的steps数据
            steps_data = []
            if hasattr(gs, 'events') and gs.events:
                # 游戏开始步骤
                steps_data.append({
                    "idx": 0,
                    "evt": "GAME_START",
                    "payload": {
                        "session_id": session_id,
                        "seed": seed,
                        "players": len(players_data)
                    }
                })
                
                # 从events生成steps (选取关键事件)
                key_events = ["deal_hole", "showdown", "win_fold", "win_showdown"]
                for i, event in enumerate(gs.events):
                    if event.get("t") in key_events:
                        steps_data.append({
                            "idx": len(steps_data),
                            "evt": event.get("t", "").upper(),
                            "payload": {k: v for k, v in event.items() if k != "t"}
                        })
                
                # 游戏结束步骤
                if outcome:
                    steps_data.append({
                        "idx": len(steps_data),
                        "evt": "GAME_END",
                        "payload": outcome
                    })
            
            replay_data = {
                # 基本信息
                "hand_id": hand_id,
                "session_id": session_id,
                "seed": seed,
                
                # 游戏数据
                "events": getattr(gs, "events", []),
                "board": list(getattr(gs, "board", [])),
                "winner": outcome.get("winner") if outcome else None,
                "best5": outcome.get("best5") if outcome else None,
                
                # 教学数据
                "players": players_data,
                "annotations": annotations_data,
                "steps": steps_data,  # 生成的基础steps数据
                
                # 元数据
                "engine_commit": ENGINE_COMMIT,
                "schema_version": SCHEMA_VERSION,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            Replay.objects.update_or_create(hand_id=hand_id, defaults={"payload": replay_data})
        except Exception as e:
            import logging
            logging.warning(f"Failed to save replay for {hand_id}: {e}")

    try:
        return Response(payload, status=status.HTTP_200_OK)
    finally:
        try:
            metrics.observe_request(route, method, "200", time.perf_counter() - t0)
        except Exception:
            pass

# ---------- 5) GET /session/{session_id}/state ----------

SessionStateResp = inline_serializer(
    name="SessionStateResp",
    fields={
        "session_id": serializers.CharField(),
        "button": serializers.IntegerField(),
        "stacks": serializers.ListField(child=serializers.IntegerField()),
        "stacks_after_blinds": serializers.ListField(child=serializers.IntegerField(), allow_null=True),
        "sb": serializers.IntegerField(),
        "bb": serializers.IntegerField(),
        "hand_counter": serializers.IntegerField(),
        "current_hand_id": serializers.CharField(required=False, allow_null=True),
    }
)

@extend_schema(responses={200: SessionStateResp})
@api_view(["GET"])
def session_state_api(request, session_id: str):
    t0 = time.perf_counter()
    route = "session/state"
    method = "GET"
    s = get_object_or_404(Session, session_id=session_id)
    # 尝试从内存映射取当前手（教学期：最后一次启动的 hand）
    current_hand_id, latest_gs = None, None
    for hid, item in reversed(list(HANDS.items())):
        if item.get("session_id") == session_id:
            current_hand_id = hid
            latest_gs = item.get("gs")
            break
    stacks_after_blinds = None
    if latest_gs:
        stacks_after_blinds = [latest_gs.players[0].stack, latest_gs.players[1].stack]
    sb = int((s.config or {}).get("sb", 1))
    bb = int((s.config or {}).get("bb", 2))
    try:
        return Response({
        "session_id": s.session_id,
        "button": s.button,
        "stacks": s.stacks,
        "stacks_after_blinds": stacks_after_blinds,
        "sb": sb,
        "bb": bb,
        "hand_counter": s.hand_counter,
        "current_hand_id": current_hand_id,
    })
    finally:
        try:
            metrics.observe_request(route, method, "200", time.perf_counter() - t0)
        except Exception:
            pass

# ---------- 6) POST /session/next ----------

NextHandResp = inline_serializer(
    name="NextHandResp",
    fields={
        "session_id": serializers.CharField(),
        "hand_id": serializers.CharField(),
        "state": serializers.JSONField(),
    }
)

@extend_schema(
    request=inline_serializer(name="NextHandReq", fields={
        "session_id": serializers.CharField(),
        "seed": serializers.IntegerField(required=False, allow_null=True),
    }),
    responses={200: NextHandResp}
)

@api_view(["POST"])
def session_next_api(request):
    t0 = time.perf_counter()
    route = "session/next"
    method = "POST"
    session_id = request.data.get("session_id")
    seed = request.data.get("seed")
    s = get_object_or_404(Session, session_id=session_id)

    # 1) 找到该会话最新且 complete 的上一手
    latest_gs, latest_cfg = None, None
    for hid, item in reversed(list(HANDS.items())):
        if item.get("session_id") == session_id:
            gs = item.get("gs")
            latest_gs = gs
            latest_cfg = item.get("cfg")
            if getattr(gs, "street", None) == "complete":
                break
    if latest_gs is None or getattr(latest_gs, "street", None) != "complete":
        try:
            metrics.observe_request(route, method, "409", time.perf_counter() - t0)
        except Exception:
            pass
        return Response({"detail": "last hand not complete"}, status=status.HTTP_409_CONFLICT)

    # 配置统一兜底到 DB
    cfg_for_next = latest_cfg or s.config

    # 计算下一手参数（按钮、堆栈、手数+1）

    # 2) 构造 Session 视图（从模型）
    sv = SessionView(
        session_id=s.session_id,
        button=int(s.button),
        stacks=tuple(s.stacks),
        hand_no=int(s.hand_counter),
        current_hand_id=None
    )

    # 3) 规划下一手
    plan = next_hand(
        sv,
        latest_gs,
        seed=seed
    )

    # 4) 更新 Session 持久层
    s.button = plan.next_button
    s.stacks = list(plan.stacks)
    s.hand_counter = plan.next_hand_no
    s.save(update_fields=["button", "stacks", "hand_counter", "updated_at"])

    # 5) 启动新手（关键：带入 plan.stacks）
    new_hid = str(uuid.uuid4())
    gs_new = _start_hand_with_carry(
        cfg_for_next, session_id=session_id, hand_id=new_hid,
        button=plan.next_button, stacks=plan.stacks, seed=plan.seed
    )
    HANDS[new_hid] = {"gs": gs_new, "session_id": session_id, "cfg": cfg_for_next}

    try:
        return Response({
        "session_id": session_id,
        "hand_id": new_hid,
        "state": snapshot_state(gs_new),
    })
    finally:
        try:
            metrics.observe_request(route, method, "200", time.perf_counter() - t0)
        except Exception:
            pass
