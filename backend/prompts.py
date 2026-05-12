"""
prompts.py — Prompt engineering & reply builder
"""

import json
from model import CostState


SYSTEM_PROMPT = """You are a Thai assistant for a Manday Cost Calculator.
Respond ONLY with valid JSON. No markdown. No extra text.

Response format:
{
  "actions": [
    {"intent": "...", "target": "...", "payload": {...}},
    ...
  ],
  "reply": "Thai reply 1-2 sentences"
}

ACTIONS — include ALL actions needed to fulfill the user's message:

1. {"intent":"add","target":"phase_item","payload":{...}}
   payload: {"phase":"...","title":"...","person":n,"times":n,"days":n,"rate":n,"rate_source":"user|inferred","fuel":n,"hotel":n,"allowance":n,"flight":n,"rental":n,"taxi":n,"travel_allow":n}
   - ค่าเดินทางต่อ item เป็น optional — parse เฉพาะที่ user ระบุมาเท่านั้น
   - ห้ามคิด cost เอง — Python จะคำนวณเอง
   - rate_source="user"     → user พูดตัวเลข rate ชัดเจนใน turn นี้
   - rate_source="inferred" → LLM เดาเอง / copy จาก item อื่น
   - If rate_source would be "inferred" → omit rate entirely, do not include it

2. {"intent":"delete","target":"phase_item","payload":{"phase":"...","title":"..."}}
   - If user says "ลบทั้งหมดใน phase X" → one delete action per existing item in that phase
   - Check [CURRENT STATE].phases to know which items exist

3. {"intent":"edit","target":"phase_item","payload":{"phase":"...","title":"...",...changed fields only...}}

4. {"intent":"set","target":"scalar","payload":{"field":"requester_name|project_name|markup_pct","value":...}}
   - One action per scalar field
   - ห้าม set fuel|hotel|allowance|flight|rental|taxi|travel_allow เป็น scalar
   - ค่าเดินทางต้องระบุต่อ item เท่านั้น ผ่าน intent=edit target=phase_item
   - ค่าเดินทาง (hotel/fuel/allowance/flight/rental/taxi/travel_allow) ต้องระบุต่อ item เท่านั้น
   - ถ้า user บอกค่าเดินทางโดยไม่ระบุชื่อ item ชัดเจน → actions MUST be [] (ห้าม edit ใดๆ ทั้งสิ้น) และ reply ถามกลับโดยแสดงรายชื่อ item ทั้งหมดจาก [CURRENT STATE].phases ให้ user เลือก
   - ห้าม assume ว่า user ต้องการทุก item — ต้องให้ user ระบุเองเสมอ
   - เฉพาะเมื่อ user พูดชื่อ item ชัดเจนในข้อความ เช่น "Setup ระบบ ค่าโรงแรม 1200" หรือตอบกลับคำถามด้วยชื่อ item → จึง edit ได้

5. {"intent":"query","target":"-","payload":{}}

PHASE MAPPING:
- prepare   = Prepare / เตรียมงาน
- implement = Implement / ติดตั้ง / ทำระบบ
- service   = Service / Support / MA / บำรุงรักษา

CONFIRMATION RULE:
- ถ้า [CURRENT STATE].pending_suggestion ไม่ว่าง และ user พูดว่า "ยืนยัน" / "ok" / "ได้เลย" / "confirm"
  → ให้สร้าง add actions จาก pending_suggestion.items ทุกตัว
  → ห้าม suggest ซ้ำอีกครั้ง

RATE-AFTER-SUGGEST RULE:
- ถ้า [CURRENT STATE].pending_suggestion ไม่ว่าง และ user ระบุ rate เช่น "ใช้ 4500 ทุก item" หรือ "Consultant 4500"
  → intent=edit ทุก item ใน pending_suggestion.items พร้อม rate ที่ user บอก
  → rate_source="user"
  → ห้าม suggest ซ้ำ
- ถ้า user ระบุ rate แยกต่อ item เช่น "Kickoff 5000, Training 3500"
  → intent=edit แยกต่อ item ตามที่ user บอก

RULES:
- Phase items are OPTIONAL — user can have 0 items in any phase, result will show 0 for that phase
- Only 3 fields required to show result: requester_name, project_name, markup_pct
- Show result immediately once those 3 are collected — do not wait for phase items
- NEVER invent numbers not stated by user
- NEVER add rate if user didn't mention it — omit rate field entirely
- NEVER copy rate from other items — each item's rate must be explicitly stated this turn
- actions array must cover EVERY piece of info the user gave
- reply: confirm what changed, 1-2 sentences Thai, no need to ask for phase items
- Convert Thai numbers: หนึ่ง=1, สอง=2, สาม=3 etc.
- "ชื่อผู้ขอ" = "ผู้จัดทำ" = "จัดทำโดย" = "requester_name" — same field
- Check [CURRENT STATE] before asking — if field already exists, do not ask again
- ถ้า user บอกค่าเดินทาง (hotel/fuel/allowance/flight/rental/taxi/travel_allow) โดยไม่ระบุ item
  → ห้าม set เป็น scalar
  → ให้ reply ถามกลับว่า "ค่าโรงแรม 1200 บาท ใช้กับหัวข้อไหนบ้างครับ?" พร้อมแสดงรายการ item ที่มีอยู่
  → actions: [] (ยังไม่ต้องทำอะไร รอ user ตอบก่อน)

- ถ้า user ระบุ item ชัดเจน เช่น "Setup ระบบ ค่าโรงแรม 1200"
  → intent=edit, target=phase_item, payload={"phase":"implement","title":"Setup ระบบ","hotel":1200}

6. {"intent":"suggest","target":"phase_items","payload":{"items":[...],"assumption":"..."}}
   - ใช้เมื่อ user บอก requirement แบบ free-text เช่น "ต้องการติดตั้ง ERP มี 3 site"
   - LLM วิเคราะห์แล้ว suggest phase_items พร้อม person/times/days
   - ⛔ ห้ามใส่ rate หรือ rate_source ใน suggest items เด็ดขาด — ละเว้น rate field ทั้งหมด
   - assumption: อธิบาย scope สมมติฐาน และแจ้งว่าจะถาม rate แยกต่างหาก
   - หลังจาก suggest → system จะถาม rate เองอัตโนมัติ ห้าม LLM ถาม rate ใน reply

RATE-AFTER-SUGGEST RULE:
- ถ้า [CURRENT STATE].pending_suggestion ไม่ว่าง และ user ระบุ rate ไม่ว่าจะรูปแบบใด:
  เช่น "ใช้ 4500 ทุก item" / "เอาตามแนะนำ" / "ตามที่แนะนำ" / "ok rate นั้น" / "ได้เลย"
  → intent=edit ทุก item ใน pending_suggestion.items พร้อม rate ที่เหมาะสม
  → rate_source="user" ถ้า user พูดตัวเลขชัด / "inferred" ถ้า user บอกให้ใช้ rate ที่ระบบแนะนำ
  → ห้าม add items ก่อนที่ user จะยืนยัน scope
  → ห้าม suggest ซ้ำ

- "เอาตามแนะนำ" / "ตามแนะนำ" / "ใช้ rate ที่แนะนำ"
  → ให้ map rate ตามประเภทงานของแต่ละ item:
     - item ที่มีคำว่า Planning/Design/Analysis/Requirement/Audit → rate=4500
     - item ที่มีคำว่า Migration/Config/Setup/Technical/Testing/Go-Live → rate=4000
     - item ที่มีคำว่า Training → rate=3500
     - item ที่มีคำว่า Support/Stabilization/Optimization/Knowledge → rate=3000
     - item อื่นๆ → rate=4000
  → intent=edit ทุก item ใน pending_suggestion พร้อม rate ที่ map ได้
  → rate_source="inferred"
"""


def state_context(state: CostState) -> str:
    d = state.data
    missing = state.missing_required()
    items = d.get("phase_items", [])

    phase_summary = {}
    for item in items:
        p = item.get("phase", "?")
        missing_fields = []
        if not item.get("person") and item.get("person") != 0:
            missing_fields.append("person")
        if not item.get("times"):
            missing_fields.append("times")
        if not item.get("days"):
            missing_fields.append("days")
        if not item.get("rate") and not item.get("cost"):
            missing_fields.append("rate")
        phase_summary.setdefault(p, []).append({
            "title":          item.get("title"),
            "rate":           item.get("rate"),
            "missing_fields": missing_fields,
        })

    waiting_rate = [
        {"phase": i["phase"], "title": i["title"]}
        for i in items
        if not i.get("rate") and not i.get("cost")
    ]

    ctx = {
        "collected": {
            "requester_name": d.get("requester_name"),
            "project_name":   d.get("project_name"),
            "markup_pct":     d.get("markup_pct"),
        },
        "phases":             phase_summary,
        "missing":            [label for _, label in missing],
        "waiting_for_rate":   waiting_rate,
        "is_complete":        state.is_complete(),
        "pending_suggestion": state.data.get("pending_suggestion"),
    }
    return (
        f"\n\n[CURRENT STATE]: {json.dumps(ctx, ensure_ascii=False)}"
        "\n[REMINDER]: JSON only. No Markdown."
        "\n[CRITICAL]: Do NOT copy rate from existing items. Only use rate if user stated it THIS turn."
        "\n[CRITICAL]: If waiting_for_rate is not empty and user gives a rate → intent=edit target=phase_item"
        "\n[CRITICAL]: If pending_suggestion is not empty → NEVER add rate to suggest items. Wait for user to provide rate."
    )

def build_messages(state: CostState, user_message: str) -> list:
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    recent = state.history[-12:] if len(state.history) > 12 else state.history
    msgs.extend(recent)
    msgs.append({"role": "user", "content": user_message + state_context(state)})
    return msgs


def build_reply(state: CostState, llm_data: dict) -> str:
    llm_reply = llm_data.get("reply", "").strip()

    if "pending_suggestion" in state.data:
        suggestion = state.data["pending_suggestion"]
        items      = suggestion.get("items", [])
        assumption = suggestion.get("assumption", "")

        # ตรวจว่า items มี rate แล้วหรือยัง
        items_with_rate    = [i for i in items if i.get("rate")]
        items_without_rate = [i for i in items if not i.get("rate")]

        lines = ["📋 **วิเคราะห์ความต้องการได้ดังนี้ครับ:**\n"]

        if items_without_rate:
            # ยังไม่มี rate → แสดง table ไม่มี rate column
            lines.append("| Phase | หัวเรื่อง | คน | ครั้ง | วัน |")
            lines.append("|---|---|---:|---:|---:|")
            for item in items:
                lines.append(
                    f"| {item.get('phase','').capitalize()} "
                    f"| {item.get('title','')} "
                    f"| {item.get('person', 1)} "
                    f"| {item.get('times', 1)} "
                    f"| {item.get('days', 1)} |"
                )
            if assumption:
                lines.append(f"\n💡 **สมมติฐาน:** {assumption}")

            lines.append("\n---")
            lines.append("✅ **Scope ดูโอเคไหมครับ?**")
            lines.append("\nกรุณาระบุ **Rate (฿/วัน)** ที่ต้องการใช้ครับ\n")
            lines.append("| ประเภทงาน | Rate แนะนำ |")
            lines.append("|---|---:|")
            lines.append("| Project Manager | ฿5,000/วัน |")
            lines.append("| Consultant / Analyst | ฿4,500/วัน |")
            lines.append("| Technical / Developer | ฿4,000/วัน |")
            lines.append("| Trainer | ฿3,500/วัน |")
            lines.append("| Support / MA | ฿3,000/วัน |")
            lines.append("\n💬 บอกได้เลยครับ เช่น:")
            lines.append('- **"ใช้ 4500 ทุก item"** — ใช้ rate เดียวทั้งหมด')
            lines.append('- **"Kickoff 5000, Training 3500, Support 3000"** — แยกต่อประเภท')

        else:
            # มี rate แล้ว → แสดง table พร้อม rate และ preview cost
            import math as _math

            def _preview_cost(item):
                person = float(item.get("person", 1) or 1)
                times  = float(item.get("times",  1) or 1)
                days   = float(item.get("days",   1) or 1)
                rate   = float(item.get("rate",   0) or 0)
                return _math.ceil(person * times * days * rate)

            total_cost     = sum(_preview_cost(i) for i in items)
            markup_pct     = float(state.data.get("markup_pct", 0) or 0)
            total_w_markup = _math.ceil(total_cost * (1 + markup_pct / 100))

            lines.append("| Phase | หัวเรื่อง | คน | ครั้ง | วัน | Rate | ประมาณการ |")
            lines.append("|---|---|---:|---:|---:|---:|---:|")
            for item in items:
                rate = item.get("rate", 0) or 0
                cost = _preview_cost(item)
                lines.append(
                    f"| {item.get('phase','').capitalize()} "
                    f"| {item.get('title','')} "
                    f"| {item.get('person', 1)} "
                    f"| {item.get('times', 1)} "
                    f"| {item.get('days', 1)} "
                    f"| ฿{rate:,} "
                    f"| ฿{cost:,} |"
                )
            lines.append(f"| | | | | | **รวมต้นทุน** | **฿{total_cost:,}** |")
            if markup_pct:
                lines.append(
                    f"| | | | | | **+Markup {markup_pct:.0f}%** | **฿{total_w_markup:,}** |"
                )
            if assumption:
                lines.append(f"\n💡 **สมมติฐาน:** {assumption}")
            lines.append("\n✅ ยืนยันใช้รายการนี้ได้เลยครับ หรือแก้ไขก่อน?")

        return "\n".join(lines)

    # 1. items ที่ขาด field บางอย่าง
    incomplete = []
    for i in state.data.get("phase_items", []):
        missing_fields = []
        if not i.get("person") and i.get("person") != 0:
            missing_fields.append("คน")
        if not i.get("times"):
            missing_fields.append("ครั้ง")
        if not i.get("days"):
            missing_fields.append("วัน/ครั้ง")
        if not i.get("rate") and not i.get("cost"):
            missing_fields.append("Rate")
        if missing_fields:
            incomplete.append((i["title"], i["phase"], missing_fields))

    if incomplete:
        title, phase, fields = incomplete[0]
        fields_str = ", ".join(fields)
        prefix = f"{llm_reply}\n\n" if llm_reply else ""
        return (
            f"{prefix}"
            f"⚠️ **{title}** ({phase}) ยังขาด: {fields_str} ครับ\n"
            f"กรุณาระบุ {fields_str} สำหรับ {title}?"
        )

    # 2. scalar fields ที่ขาด
    missing = state.missing_required()
    scalar_missing = [(k, l) for k, l in missing if not k.endswith("_items")]
    if scalar_missing:
        key, label = scalar_missing[0]
        prefix = f"{llm_reply}\n\n" if llm_reply else ""
        return f"{prefix}📝 ยังขาด **{label}** ครับ — กรุณาระบุ?"

    # 3. ครบแล้ว
    if state.is_complete():
        prefix = f"{llm_reply}\n\n" if llm_reply else ""
        return prefix + format_result(state.calculate())

    # 4. fallback
    return llm_reply or "มีข้อมูลอะไรเพิ่มเติมไหมครับ?"


def format_result(r: dict) -> str:
    def baht(n): return f"฿{n:,.0f}"
    def manday(n): return f"{n:,.1f}".rstrip('0').rstrip('.')  # 270 → "270", 2.5 → "2.5"

    lines = [
        f"## 🎯 ผลการคำนวณ — {r['project_name']}",
        f"*จัดทำโดย: {r['requester_name']}*",
        "",
        "| รายการ | มูลค่า |",
        "|---|---|",
        f"| Manday รวม | {manday(r['manday'])} วัน |",
        f"| Prepare Phase | {phase_summary(r['phase_costs'][0])} |",
        f"| Implement Phase | {phase_summary(r['phase_costs'][1])} |",
        f"| Service Phase | {phase_summary(r['phase_costs'][2])} |",
        f"| **รวมต้นทุน 3 Phase** | **{baht(r.get('subtotal_cost', 0))}** |",
        f"| Markup / กำไร {r['markup_pct']}% | {baht(r.get('profit', 0))} |",
        f"| ค่าเดินทางรวม | {baht(r.get('travel_cost', 0))} |",
        f"| 🏆 **ยอดรวมทั้งหมด** | 🏆 **{baht(r['total'])}** |",
        "",
        "| Phase | หัวเรื่อง | Manday | ต้นทุน |",
        "|---|---|---:|---:|",
    ]
    for phase in r["phase_costs"]:
        for item in phase.get("items", []):
            lines.append(
                f"| {phase['label']} | {item['title']} | {manday(item['manday'])} | {baht(item['cost'])} |"
            )
    lines += [
        "",
        "---",
        "💡 แก้ไขตัวเลขหรือเพิ่มค่าเดินทางได้เลยครับ",
        "📊 กด **Export Excel** หรือ **Export PDF** เพื่อดาวน์โหลดรายงาน",
    ]
    return "\n".join(lines)


def phase_summary(p: dict) -> str:
    def baht(n): return f"฿{n:,.0f}"
    def manday(n): return f"{n:,.1f}".rstrip('0').rstrip('.')
    return f"{len(p.get('items', []))} หัวข้อ / {manday(p['manday'])} manday = {baht(p['cost'])}"