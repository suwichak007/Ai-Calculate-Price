"""
llm.py — LLM integration via Groq API
"""

import json
import re
import os
from groq import Groq
import anthropic


def load_llm():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ไม่พบ ANTHROPIC_API_KEY ใน environment variables")
    return anthropic.Anthropic(api_key=api_key)


def call_llm(client, messages: list) -> str:
    # แยก system message ออกมา
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
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    open_count  = raw.count('{')
    close_count = raw.count('}')
    if open_count > close_count:
        patched = raw + ('}' * (open_count - close_count))
        try:
            return json.loads(patched)
        except json.JSONDecodeError:
            pass

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

    return {"actions": [], "reply": ""}

def expand_scope(client, user_message: str) -> str:
    """
    Step 1: Think like a PM — concise, realistic scope
    """
    res = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1500,
        system="""You are a senior Thai IT Project Manager with 15 years of ERP/CRM/HRM implementation experience.

Analyze the requirement and produce a CONCISE project scope. 

GUIDELINES:
- Group related tasks — ห้ามแตก task ย่อยเกินไป (max 6-8 items per phase)
- ประมาณ จำนวนคน/วัน ให้สมจริงตาม project size
- Multi-site: แยก task เฉพาะที่ต้องทำแยก site จริงๆ (training, go-live) ไม่ใช่ทุก task
- ถ้า task ทำพร้อมกันได้หรือคล้ายกันมาก → รวมไว้ใน item เดียว เพิ่ม "คน" แทน

REALISTIC SIZING สำหรับ ERP 3 site, SME (50-200 users):
- Prepare phase: รวม 6-10 สัปดาห์ (30-50 วัน)
- Implement phase: รวม 10-16 สัปดาห์ (50-80 วัน)  
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
- จำนวนวันต้องสมเหตุสมผล — "ERP Installation + Config" ทั้งหมดไม่ควรเกิน 20 วัน/คน
- Training แยก Key User vs End User แต่รวม site ไว้ด้วยกัน (เพิ่ม person แทน)
- Data Migration รวมทั้ง 3 site ใน 1 item (เพิ่ม person หรือวัน)""",
        messages=[{"role": "user", "content": f"Project requirement: {user_message}"}]
    )
    return res.content[0].text.strip()


def requirement_to_actions(client, original_msg: str, expanded_scope: str) -> str:
    """
    Step 2: Convert concise PM scope → JSON actions
    """
    from prompts import SYSTEM_PROMPT

    combined_user_content = f"""Original requirement: {original_msg}

[Project Manager Scope Analysis]:
{expanded_scope}

[INSTRUCTION]:
- สร้าง intent=suggest จาก scope ข้างบน
- แปลง แต่ละ bullet → 1 phase_item
- rate_source="inferred" ทุกตัว
- rate ตามประเภทงาน:
    PM / Project Management = 5000
    Consultant / Analysis / Design = 4500
    Technical / Dev / Config = 4000
    Training = 3500
    Support / MA = 3000
- person/times/days ให้ใช้ตามที่ PM Analysis ระบุ
- ห้ามแตก item เพิ่มเองนอกจากที่ PM Analysis ระบุ
- assumption: สรุปสมมติฐาน project size, จำนวน site/user, และ rate ที่ใช้

SIZING SANITY CHECK ก่อน output:
- Prepare รวมทุก item ไม่เกิน 50 วัน
- Implement รวมทุก item ไม่เกิน 80 วัน  
- Service แต่ละ item ไม่เกิน 30 วัน
- ถ้าเกิน → ลด days หรือเพิ่ม person แทน"""

    res = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": combined_user_content}]
    )
    return res.content[0].text.strip()

def is_free_text_requirement(msg: str) -> bool:
    """ตรวจว่าควร trigger two-step flow ไหม"""
    msg_lower = msg.lower()
    
    trigger_keywords = [
        "ติดตั้ง", "วางระบบ", "implement", "deploy",
        "erp", "crm", "hrm", "wms", "scm", "pos",
        "ต้องการระบบ", "โปรเจค", "project",
        "training", "อบรม", "site",
    ]
    
    skip_prefixes = ["ลบ", "แก้ไข", "เพิ่ม", "set ", "reset", "export", "ยืนยัน", "ok"]
    
    has_trigger = any(k in msg_lower for k in trigger_keywords)
    is_command = any(msg_lower.startswith(p) for p in skip_prefixes)
    is_long_enough = len(msg.strip()) > 15
    
    return has_trigger and not is_command and is_long_enough