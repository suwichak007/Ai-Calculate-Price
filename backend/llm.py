"""
llm.py — LLM integration
  - load_llm()        : โหลด Llama model (หรือ None ถ้าไม่มี)
  - call_llm()        : ส่ง messages ไปยัง model / mock
  - mock_extract()    : regex fallback เมื่อไม่มี model
  - parse_llm_response() : แปลง raw JSON string → dict
"""

import json
import re
from pathlib import Path

# ── Model config ──────────────────────────────────────────────

MODEL_PATH = "meta-llama-3-8b-instruct.Q4_K_M.gguf"

# ── Loader ────────────────────────────────────────────────────

def load_llm():
    """Return Llama instance or None (mock mode)."""
    try:
        from llama_cpp import Llama
    except ImportError:
        print("⚠️  llama-cpp-python ไม่ได้ติดตั้ง — เปิด mock mode")
        return None

    if not Path(MODEL_PATH).exists():
        print("⚠️  ไม่พบโมเดล — เปิด mock mode (demo only)")
        return None

    print(f"⏳ กำลังโหลดโมเดล: {MODEL_PATH}")
    llm = Llama(
        model_path=MODEL_PATH,
        n_ctx=4096,
        n_threads=8,
        n_gpu_layers=0,
        verbose=False,
    )
    print("✅ โหลดโมเดลสำเร็จ")
    return llm


# ── Inference ─────────────────────────────────────────────────

def call_llm(llm, messages: list) -> str:
    """Call real model or fall back to mock."""
    if llm is None:
        return mock_extract(messages[-1]["content"])

    response = llm.create_chat_completion(
        messages=messages,
        max_tokens=10000,
        temperature=0.1,
        top_p=0.9,
        stop=["<|eot_id|>", "<|end_of_text|>"],
    )
    return response["choices"][0]["message"]["content"].strip()


# ── Mock (regex-based fallback) ───────────────────────────────

def mock_extract(text: str) -> str:
    """
    Simple regex extraction used when no LLM is available.
    Handles basic Thai numeric phrases and common field keywords.
    """
    extracted = {}
    block_items = parse_phase_items_from_block(text)
    if block_items:
        extracted["phase_items"] = block_items

    phase_aliases = {
        "prepare": r"(?:prepare|preparation|เตรียมงาน)",
        "implement": r"(?:implement|implementation|ติดตั้ง|ทำระบบ)",
        "service": r"(?:service|support|maintenance|บำรุงรักษา)",
    }
    for phase, alias in phase_aliases.items():
        m = re.search(
            alias + r"(?P<body>.*?)(?=(?:prepare|preparation|เตรียมงาน|implement|implementation|ติดตั้ง|ทำระบบ|service|support|maintenance|บำรุงรักษา)|$)",
            text,
            re.IGNORECASE,
        )
        if not m:
            continue
        body = m.group("body")
        phase_patterns = {
            "person": r"(\d+)\s*(?:คน|ท่าน|people|person)",
            "days": r"(\d+)\s*(?:วัน|day)",
            "times": r"(\d+)\s*(?:ครั้ง|time|visit)",
            "rate": r"(?:rate|ราคา|ค่าแรง)[^\d]*(\d[\d,]*)",
            "cost": r"(?:รวม|total|cost|ต้นทุนรวม|ราคารวม)[^\d]*(\d[\d,]*)",
        }
        for field, pat in phase_patterns.items():
            pm = re.search(pat, body, re.IGNORECASE)
            if pm:
                extracted[f"{phase}_{field}"] = float(pm.group(1).replace(",", ""))

    patterns = {
        "implement_person": r"(\d+)\s*(?:คน|ท่าน|people|person)",
        "implement_days":   r"(\d+)\s*(?:วัน|day)",
        "implement_times":  r"(\d+)\s*(?:ครั้ง|time|visit)",
        "implement_rate":   r"(?:rate|ราคา|ค่าแรง)[^\d]*(\d[\d,]*)",
        "markup_pct":     r"(?:markup|กำไร)[^\d]*(\d+)\s*%",
        "prepare_cost":   r"(?:prepare|preparation|เตรียมงาน).*?(?:รวม|total|cost|ต้นทุนรวม|ราคารวม)[^\d]*(\d[\d,]*)",
        "implement_cost": r"(?:implement|implementation).*?(?:รวม|total|cost|ต้นทุนรวม|ราคารวม)[^\d]*(\d[\d,]*)",
        "service_cost":   r"(?:service|support|maintenance|บำรุงรักษา).*?(?:รวม|total|cost|ต้นทุนรวม|ราคารวม)[^\d]*(\d[\d,]*)",
        "requester_name": r"(?:ผู้ขอ|จัดทำโดย|ชื่อ(?:ผม|ฉัน|หนู)?(?:คือ|ว่า)?)[:\s]*([^\d,\n]{2,20})",
        "project_name":   r"(?:โครงการ|project|ลูกค้า)[:\s]*([^\d,\n]{2,40})",
    }
    for key, pat in patterns.items():
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = m.group(1).replace(",", "").strip()
            extracted.setdefault(key, val if key in ("requester_name", "project_name") else float(val))

    return json.dumps({
        "extracted": extracted,
        "understood": f"รับข้อมูล: {text[:60]}",
        "needs_clarification": False,
    })


def parse_phase_items_from_block(text: str) -> list[dict]:
    phase_by_header = {
        "prepare": "prepare",
        "implement": "implement",
        "service": "service",
    }
    items = []
    current_phase = None
    current_item = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        header = line.rstrip(":").strip().lower()
        if header in phase_by_header:
            if current_item and current_phase:
                current_item["phase"] = current_phase
                items.append(current_item)
            current_phase = phase_by_header[header]
            current_item = None
            continue

        if current_phase and re.match(r"^-\s*(?:หัวข้อ|title)\s*:", line, re.IGNORECASE):
            if current_item:
                current_item["phase"] = current_phase
                items.append(current_item)
            title = line.split(":", 1)[1].strip()
            current_item = {"title": title}
            continue

        if not current_item:
            continue
        field_map = {
            "คน": "person",
            "person": "person",
            "ครั้ง": "times",
            "times": "times",
            "time": "times",
            "วัน/ครั้ง": "days",
            "วัน": "days",
            "days": "days",
            "day": "days",
            "rate": "rate",
            "cost": "cost",
            "รวม": "cost",
        }
        if ":" not in line:
            continue
        key, value = [x.strip() for x in line.split(":", 1)]
        mapped = field_map.get(key.lower())
        if not mapped:
            mapped = field_map.get(key)
        if mapped:
            m = re.search(r"\d[\d,]*", value)
            if m:
                current_item[mapped] = float(m.group().replace(",", ""))

    if current_item and current_phase:
        current_item["phase"] = current_phase
        items.append(current_item)
    return [i for i in items if i.get("title") and ("cost" in i or {"person", "times", "days", "rate"} <= set(i))]


# ── Response parser ───────────────────────────────────────────

def parse_llm_response(raw: str) -> dict:
    raw = raw.strip()
    
    # ลอง parse ตรงๆ ก่อน
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # หา { ... } block
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # ── ใหม่: ถ้า JSON ขาด closing } ให้ลองปิดแล้ว parse ──
    # นับ { และ } แล้วเติมให้ครบ
    open_count  = raw.count('{')
    close_count = raw.count('}')
    if open_count > close_count:
        patched = raw + ('}' * (open_count - close_count))
        try:
            return json.loads(patched)
        except json.JSONDecodeError:
            pass

    # ── ใหม่: ดึง actions array แม้ JSON ไม่สมบูรณ์ ──
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