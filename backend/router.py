"""
router.py — FastAPI route handlers
"""

import json
import io
import re
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
from datetime import datetime

from model import CostState, ChatRequest, ChatResponse
from llm import call_llm, parse_llm_response
from prompts import build_messages, build_reply
from export_excel import generate_excel
from export_pdf import generate_pdf
from urllib.parse import quote

router = APIRouter()

# ── Session store ─────────────────────────────────────────────

sessions: dict[str, CostState] = {}

def get_session(session_id: str) -> CostState:
    if session_id not in sessions:
        sessions[session_id] = CostState()
    return sessions[session_id]


# ── LLM instance ──────────────────────────────────────────────

_llm = None

def set_llm(llm_instance):
    global _llm
    _llm = llm_instance


# ── State manager — single source of truth ────────────────────

def apply_llm_action(state: CostState, llm_data: dict):
    # Support both new {actions:[...]} format and legacy single-action format
    actions = llm_data.get("actions")
    if actions and isinstance(actions, list):
        for action in actions:
            _apply_single_action(state, action)
    else:
        # Legacy fallback: top-level intent/target/payload
        _apply_single_action(state, llm_data)


def _apply_single_action(state: CostState, action: dict):
    intent  = action.get("intent", "query")
    target  = action.get("target", "")
    payload = action.get("payload", {})

    if not isinstance(payload, (dict, list)):
        return

    # bulk: scalars + items in one message
    if intent == "add" and isinstance(payload, dict) and "items" in payload:
        for s in payload.get("scalars", []):
            if isinstance(s, dict) and "field" in s:
                state.data[s["field"]] = s["value"]
        _add_items(state, payload["items"])
        return

    if intent == "add" and target == "phase_item":
        items = payload if isinstance(payload, list) else [payload]
        _add_items(state, items)

    elif intent == "delete" and target == "phase_item":
        phase = str(payload.get("phase", "")).lower()
        title = str(payload.get("title", "")).strip().lower()
        state.data["phase_items"] = [
            i for i in state.data.get("phase_items", [])
            if not (i["phase"] == phase and i["title"].strip().lower() == title)
        ]

    elif intent == "edit" and target == "phase_item":
        phase = str(payload.get("phase", "")).lower()
        title = str(payload.get("title", "")).strip().lower()
        for item in state.data.get("phase_items", []):
            if item["phase"] == phase and item["title"].strip().lower() == title:
                for k in ("person", "times", "days", "rate", "cost",
                          "fuel", "hotel", "allowance", "flight",
                          "rental", "taxi", "travel_allow"):
                    if k in payload:
                        item[k] = payload[k]

    elif intent == "set" and target == "scalar":
        items = payload if isinstance(payload, list) else [payload]
        for s in items:
            if isinstance(s, dict) and "field" in s:
                state.data[s["field"]] = s["value"]


def _add_items(state: CostState, items: list):
    state.data.setdefault("phase_items", [])
    existing = {
        (i["phase"], i["title"].strip().lower())
        for i in state.data["phase_items"]
    }
    for item in items:
        if not isinstance(item, dict) or not item.get("title"):
            continue
        item["phase"] = str(item.get("phase", "implement")).lower()
        key = (item["phase"], item["title"].strip().lower())
        if key not in existing:
            state.data["phase_items"].append(item)
            existing.add(key)


# ── Chat ──────────────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    state    = get_session(req.session_id)
    user_msg = req.message.strip()

    # reset
    if user_msg.lower() in ("reset", "เริ่มใหม่", "clear"):
        sessions[req.session_id] = CostState()
        return ChatResponse(
            reply="🔄 เริ่มต้นใหม่แล้วครับ! บอกชื่อผู้ขอและรายละเอียดโครงการได้เลย",
            state_summary={},
            is_complete=False,
        )

    # debug export
    if user_msg.lower() == "export":
        if state.is_complete():
            result = state.calculate()
            return ChatResponse(
                reply=f"```json\n{json.dumps(result, ensure_ascii=False, indent=2)}\n```",
                state_summary=state.data,
                is_complete=True,
                result=result,
            )
        return ChatResponse(
            reply="⚠️ ยังกรอกข้อมูลไม่ครบ",
            state_summary=state.data,
            is_complete=False,
        )

    # normal flow
    state.add_history("user", user_msg)
    messages = build_messages(state, user_msg)
    raw      = call_llm(_llm, messages)
    llm_data = parse_llm_response(raw)

    print("=== LLM RAW ===\n", raw)
    print("=== PARSED ===\n", llm_data)

    # retry ถ้า parse ได้ empty
    if not llm_data.get("intent") and not llm_data.get("reply"):
        messages[-1]["content"] += "\n\n[IMPORTANT: respond in JSON only, no markdown]"
        raw2     = call_llm(_llm, messages)
        llm_data = parse_llm_response(raw2)

    apply_llm_action(state, llm_data)   # ← จุดเดียวที่แตะ state

    reply  = build_reply(state, llm_data)
    state.add_history("assistant", reply)
    result = state.calculate() if state.is_complete() else None

    return ChatResponse(
        reply=reply,
        state_summary=state.data,
        is_complete=state.is_complete(),
        result=result,
    )


# ── Export ────────────────────────────────────────────────────

@router.get("/export/excel/{session_id}")
async def export_excel(session_id: str):
    state = get_session(session_id)
    if not state.is_complete():
        return HTMLResponse("⚠️ ข้อมูลไม่ครบ", status_code=400)
    result   = state.calculate()
    data     = generate_excel(result)
    safe     = re.sub(r"[^\w\-]", "_", result["project_name"])
    filename = f"manday_{safe}_{datetime.now().strftime('%Y%m%d')}.xlsx"
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.get("/export/pdf/{session_id}")
async def export_pdf(session_id: str):
    state = get_session(session_id)
    if not state.is_complete():
        return HTMLResponse("⚠️ ข้อมูลไม่ครบ", status_code=400)
    result   = state.calculate()
    data     = generate_pdf(result)
    safe     = re.sub(r"[^\w\-]", "_", result["project_name"])
    filename = f"manday_{safe}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


# ── Session ───────────────────────────────────────────────────

@router.get("/session/{session_id}")
async def get_session_info(session_id: str):
    state = get_session(session_id)
    return {
        "data":        state.data,
        "missing":     state.missing_required(),
        "is_complete": state.is_complete(),
        "result":      state.calculate() if state.is_complete() else None,
    }

@router.delete("/session/{session_id}")
async def clear_session(session_id: str):
    if session_id in sessions:
        del sessions[session_id]
    return {"status": "cleared"}


# ── Health ────────────────────────────────────────────────────

@router.get("/health")
async def health():
    return {
        "status":       "ok",
        "model_loaded": _llm is not None,
        "mock_mode":    _llm is None,
    }


# ── Frontend ──────────────────────────────────────────────────

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

@router.get("/")
async def serve_html():
    p = FRONTEND_DIR / "chatbot_frontend.html"
    if p.exists():
        return FileResponse(str(p))
    return HTMLResponse("<h2>ไม่พบ chatbot_frontend.html</h2>", status_code=404)

@router.get("/chatbot_frontend.css")
async def serve_css():
    p = FRONTEND_DIR / "chatbot_frontend.css"
    if p.exists():
        return FileResponse(str(p), media_type="text/css")
    return HTMLResponse("/* not found */", status_code=404)

@router.get("/chatbot_frontend.js")
async def serve_js():
    p = FRONTEND_DIR / "chatbot_frontend.js"
    if p.exists():
        return FileResponse(str(p), media_type="application/javascript")
    return HTMLResponse("// not found", status_code=404)