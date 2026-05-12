"""
llm.py — LLM integration via Anthropic API
"""

import json
import re
import os
import anthropic


def load_llm():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ไม่พบ ANTHROPIC_API_KEY ใน environment variables")
    return anthropic.Anthropic(api_key=api_key)


def call_llm(client, messages: list) -> str:
    system_prompt = ""
    filtered_messages = []
    for msg in messages:
        if msg["role"] == "system":
            system_prompt = msg["content"]
        else:
            filtered_messages.append(msg)

    res = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=5000,
        system=system_prompt,
        messages=filtered_messages,
    )
    return res.content[0].text.strip()


def parse_llm_response(raw: str) -> dict:
    raw = raw.strip()

    # ลบ markdown code block ถ้ามี
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        raw = raw.strip()

    # 1. parse ตรงๆ
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # 2. หา JSON object แรกที่สมบูรณ์
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # 3. patch วงเล็บที่ขาด (truncated)
    open_count  = raw.count('{')
    close_count = raw.count('}')
    open_arr    = raw.count('[')
    close_arr   = raw.count(']')

    if open_count > close_count or open_arr > close_arr:
        patched = raw
        if open_arr > close_arr:
            patched += ']' * (open_arr - close_arr)
        if open_count > close_count:
            patched += '}' * (open_count - close_count)
        try:
            return json.loads(patched)
        except json.JSONDecodeError:
            pass

    # 4. ดึง actions array ที่สมบูรณ์
    actions_match = re.search(r'"actions"\s*:\s*(\[.*?\])', raw, re.DOTALL)
    reply_match   = re.search(r'"reply"\s*:\s*"([^"]*)"', raw)
    if actions_match:
        try:
            actions = json.loads(actions_match.group(1))
            return {
                "actions": actions,
                "reply": reply_match.group(1) if reply_match else "",
            }
        except json.JSONDecodeError:
            pass

    # 5. ดึง partial actions — เอาเฉพาะ items ที่ parse ได้
    partial_match = re.search(r'"actions"\s*:\s*\[(.*)', raw, re.DOTALL)
    if partial_match:
        items_raw  = partial_match.group(1)
        valid_items = []
        for obj_match in re.finditer(r'\{[^{}]*\}', items_raw, re.DOTALL):
            try:
                obj = json.loads(obj_match.group())
                valid_items.append(obj)
            except json.JSONDecodeError:
                continue
        if valid_items:
            print(f"=== PARTIAL PARSE: recovered {len(valid_items)} actions ===")
            return {
                "actions": valid_items,
                "reply": reply_match.group(1) if reply_match else "",
            }

    return {"actions": [], "reply": ""}


def expand_scope(client, user_message: str) -> str:
    """
    Step 1: Think like a PM — concise, realistic scope (plain text, no JSON)
    """
    res = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1500,
        system="""You are a senior Thai IT Project Manager with 15 years of ERP/CRM/HRM implementation experience.

Analyze the requirement and produce a CONCISE project scope.

GUIDELINES:
- Group related tasks — ห้ามแตก task ย่อยเกินไป (max 5-7 items per phase)
- ประมาณ จำนวนคน/วัน ให้สมจริงตาม project size
- Multi-site: แยก task เฉพาะที่ต้องทำแยก site จริงๆ (training, go-live) ไม่ใช่ทุก task
- ถ้า task ทำพร้อมกันได้หรือคล้ายกันมาก → รวมไว้ใน item เดียว เพิ่ม "คน" แทน

REALISTIC SIZING สำหรับ ERP 3 site, SME (50-200 users):
- Prepare phase: รวม 6-10 สัปดาห์ (30-50 วัน-คน)
- Implement phase: รวม 10-16 สัปดาห์ (50-80 วัน-คน)
- Service phase: 6-12 เดือนแรก

OUTPUT FORMAT (กระชับ ต่อ phase):
PREPARE:
- [task name] | คน: X | วัน: Y | หมายเหตุ: ...

IMPLEMENT:
- [task name] | คน: X | ครั้ง: Z | วัน: Y | หมายเหตุ: ...

SERVICE:
- [task name] | คน: X | วัน: Y | หมายเหตุ: ...

RULES:
- Prepare: max 5 items
- Implement: max 7 items
- Service: max 4 items
- จำนวนวันต้องสมเหตุสมผล — ERP Installation + Config ทั้งหมดไม่ควรเกิน 20 วัน/คน
- Training แยก Key User vs End User แต่รวม site ไว้ด้วยกัน (เพิ่ม person แทน)
- Data Migration รวมทั้ง 3 site ใน 1 item (เพิ่ม person หรือวัน)
- ห้ามใส่ rate หรือราคาใดๆ ทั้งสิ้น""",
        messages=[{"role": "user", "content": f"Project requirement: {user_message}"}]
    )
    return res.content[0].text.strip()


def _strip_rate_from_suggest(raw: str) -> str:
    """
    Guarantee: ลบ rate/rate_source ออกจาก suggest items เสมอ
    ไม่พึ่ง LLM ให้ทำถูก — enforce ที่ Python แทน
    """
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return raw  # parse ไม่ได้ ให้ parse_llm_response จัดการต่อ

    actions = data.get("actions", [])
    for action in actions:
        if action.get("intent") == "suggest" and action.get("target") == "phase_items":
            for item in action.get("payload", {}).get("items", []):
                item.pop("rate", None)
                item.pop("rate_source", None)
                # ensure required fields มีค่าเสมอ
                item.setdefault("times", 1)
                item.setdefault("person", 1)
                item.setdefault("days", 1)

    return json.dumps(data, ensure_ascii=False)


def requirement_to_actions(client, original_msg: str, expanded_scope: str) -> str:
    """
    Step 2: Convert concise PM scope → JSON actions (suggest intent, no rate)
    """
    from prompts import SYSTEM_PROMPT

    combined_user_content = f"""Original requirement: {original_msg}

[Project Manager Scope Analysis]:
{expanded_scope}

[INSTRUCTION]:
- สร้าง intent=suggest จาก scope ข้างบน
- แปลงแต่ละ bullet → 1 phase_item
- ⛔ ห้ามใส่ rate หรือ rate_source ใน items เด็ดขาด ไม่ว่ากรณีใดทั้งสิ้น
- person/times/days ให้ใช้ตามที่ PM Analysis ระบุ
- times ต้องมีทุก item ถ้าไม่ระบุให้ใส่ 1
- ห้ามแตก item เพิ่มเองนอกจากที่ PM Analysis ระบุ
- assumption: สรุปสมมติฐาน scope และแจ้งว่าจะถาม rate แยกต่างหาก"""

    res = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": combined_user_content}]
    )
    raw = res.content[0].text.strip()

    # Enforce: ลบ rate ออกเสมอ ไม่ว่า LLM จะใส่มาหรือไม่
    return _strip_rate_from_suggest(raw)


def is_free_text_requirement(msg: str) -> bool:
    """ตรวจว่าควร trigger two-step flow ไหม"""
    msg_lower = msg.lower()

    trigger_keywords = [
        "ติดตั้ง", "วางระบบ", "implement", "deploy",
        "erp", "crm", "hrm", "wms", "scm", "pos",
        "ต้องการระบบ", "โปรเจค", "project",
        "training", "อบรม", "site",
    ]

    skip_prefixes = [
        "ลบ", "แก้ไข", "เพิ่ม", "set ", "reset",
        "export", "ยืนยัน", "ok", "เอาตาม", "ใช้",
    ]

    has_trigger   = any(k in msg_lower for k in trigger_keywords)
    is_command    = any(msg_lower.startswith(p) for p in skip_prefixes)
    is_long_enough = len(msg.strip()) > 15

    return has_trigger and not is_command and is_long_enough