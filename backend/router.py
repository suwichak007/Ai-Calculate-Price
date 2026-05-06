"""
router.py — FastAPI route handlers  (v1.3 — + Excel Upload)
"""

import json
import io
import re
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
from datetime import datetime

from model import CostState, ChatRequest, ChatResponse
from llm import call_llm, parse_llm_response
from prompts import build_messages, build_reply
from export_excel import generate_excel
from export_pdf import generate_pdf
from parse_excel import parse_project_excel
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
    actions = llm_data.get("actions")
    if actions and isinstance(actions, list):
        for action in actions:
            _apply_single_action(state, action)
    else:
        _apply_single_action(state, llm_data)


def _apply_single_action(state: CostState, action: dict):
    intent  = action.get("intent", "query")
    target  = action.get("target", "")
    payload = action.get("payload", {})

    if not isinstance(payload, (dict, list)):
        return

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
                
    elif intent == "suggest" and target == "phase_items":
        state.data["pending_suggestion"] = {
            "items":      payload.get("items", []),
            "assumption": payload.get("assumption", ""),
        }


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

    if user_msg.lower() in ("reset", "เริ่มใหม่", "clear"):
        sessions[req.session_id] = CostState()
        return ChatResponse(
            reply="🔄 เริ่มต้นใหม่แล้วครับ! บอกชื่อผู้ขอและรายละเอียดโครงการได้เลย",
            state_summary={},
            is_complete=False,
        )

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

    state.add_history("user", user_msg)
    messages = build_messages(state, user_msg)
    raw      = call_llm(_llm, messages)
    llm_data = parse_llm_response(raw)

    print("=== LLM RAW ===\n", raw)
    print("=== PARSED ===\n", llm_data)

    if not llm_data.get("intent") and not llm_data.get("reply"):
        messages[-1]["content"] += "\n\n[IMPORTANT: respond in JSON only, no markdown]"
        raw2     = call_llm(_llm, messages)
        llm_data = parse_llm_response(raw2)

    apply_llm_action(state, llm_data)

    reply  = build_reply(state, llm_data)
    state.add_history("assistant", reply)
    result = state.calculate() if state.is_complete() else None

    return ChatResponse(
        reply=reply,
        state_summary=state.data,
        is_complete=state.is_complete(),
        result=result,
    )


# ── Excel Upload ───────────────────────────────────────────────

@router.post("/upload/excel/{session_id}")
async def upload_excel(session_id: str, file: UploadFile = File(...)):
    """
    รับไฟล์ Excel (.xlsx) รูปแบบ Project Plan
    → parse หัวเรื่องย่อย + Man Day
    → merge เข้า CostState
    → ส่งคืน ChatResponse เพื่อให้ frontend แสดงผลได้เลย
    """

    raw    = await file.read()
    parsed = parse_project_excel(raw, llm_instance=_llm)

    # เพิ่มบรรทัดนี้ชั่วคราว
    print("=== PARSED EXCEL ===", parsed)

    if not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="รองรับเฉพาะไฟล์ .xlsx / .xls")

    if "error" in parsed:
        raise HTTPException(status_code=500, detail=parsed["error"])

    state = get_session(session_id)

    print("=== EXISTING ITEMS ===", state.data.get("phase_items", []))
    print("=== EXISTING KEYS ===", {(i["phase"], i["title"].strip().lower()) for i in state.data.get("phase_items", [])})

    # อัพเดท project_name ถ้ายังไม่มี
    if parsed.get("project_name") and "project_name" not in state.data:
        state.data["project_name"] = parsed["project_name"]

    # merge phase_items (ไม่ซ้ำ title+phase)
    state.data.setdefault("phase_items", [])
    existing_keys = {
        (i["phase"], i["title"].strip().lower())
        for i in state.data["phase_items"]
    }
    added = []
    for item in parsed.get("phase_items", []):
        key = (item["phase"], item["title"].strip().lower())
        print(f"=== CHECKING KEY === {key} | in existing: {key in existing_keys}")  # ← เพิ่ม
        if key not in existing_keys:
            state.data["phase_items"].append(item)
            existing_keys.add(key)
            added.append(item)
    print("=== ADDED ===", len(added))  # ← เพิ่ม

    # สร้าง reply
    total       = len(added)
    phase_count: dict[str, int] = {}
    for it in added:
        phase_count[it["phase"]] = phase_count.get(it["phase"], 0) + 1

    label_map   = {"prepare": "Prepare", "implement": "Implement", "service": "Service"}
    phase_lines = [
        f"  • {label_map.get(ph, ph)}: {cnt} หัวเรื่อง"
        for ph, cnt in phase_count.items()
    ]

    warnings_text = ""
    if parsed.get("warnings"):
        warnings_text = "\n\n⚠️ **หมายเหตุ:**\n" + "\n".join(
            f"  - {w}" for w in parsed["warnings"]
        )

    missing      = state.missing_required()
    missing_hint = ""
    if missing:
        labels       = [l for _, l in missing]
        missing_hint = f"\n\n📝 ยังขาด: **{', '.join(labels)}** — กรุณาระบุเพิ่มเติมในแชทครับ"

    project_info = f"**{parsed['project_name']}**" if parsed.get("project_name") else f"**{file.filename}**"

    if added:
        reply = (
            f"✅ อัพโหลด {project_info} สำเร็จครับ!\n\n"
            f"นำเข้า **{total} หัวเรื่อง**:\n" + "\n".join(phase_lines) +
            "\n\n💡 **หมายเหตุ:** ยังไม่มี Rate (฿/วัน) — "
            "กรุณาระบุ Rate ของแต่ละหัวเรื่อง และ Markup % เพื่อคำนวณราคาขายครับ" +
            warnings_text + missing_hint
        )
    else:
        reply = (
            f"ℹ️ ไม่พบหัวเรื่องใหม่ใน {project_info} "
            "(อาจซ้ำกับที่มีอยู่แล้ว หรือรูปแบบ Excel ไม่ตรง)"
        )

    state.add_history("user", f"[อัพโหลดไฟล์ Excel: {file.filename}]")
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