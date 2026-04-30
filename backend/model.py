"""
models.py — Data models
  - CostState  : session state + calculation logic
  - ChatRequest / ChatResponse : Pydantic API schemas
"""

from typing import Optional
from pydantic import BaseModel


# ── Session state ─────────────────────────────────────────────

class CostState:
    PHASES = {
        "prepare": "Prepare",
        "implement": "Implement",
        "service": "Service",
    }

    REQUIRED_FIELDS = {
        "requester_name": "ชื่อผู้ขอ / ผู้จัดทำ",
        "project_name":   "ชื่อโครงการ / ลูกค้า",
        "markup_pct":     "Markup % (บวกเพิ่มจากต้นทุน)",
    }

    OPTIONAL_FIELDS = {
        "prepare_cost":  "ต้นทุน Prepare รวม (฿)",
        "implement_cost": "ต้นทุน Implement รวม (฿)",
        "service_cost":  "ต้นทุน Service รวม (฿)",
        "fuel":          "ค่าน้ำมัน (฿/วัน)",
        "hotel":         "ค่าโรงแรม (฿/วัน)",
        "allowance":     "เบี้ยเลี้ยง (฿/วัน)",
        "flight":        "ค่าเครื่องบิน (฿/เที่ยว)",
        "rental":        "ค่าเช่ารถ (฿/วัน)",
        "taxi":          "ค่า Taxi (฿/วัน)",
        "travel_allow":  "เบี้ยเดินทาง (฿/วัน)",
        "support_cost":  "ค่า Support/Service รวม (฿) — ถ้ามี",
    }

    def __init__(self):
        self.data: dict = {}
        self.history: list = []

    def missing_required(self) -> list[tuple[str, str]]:
        return [
            (key, label)
            for key, label in self.REQUIRED_FIELDS.items()
            if key not in self.data
        ]

    def _phase_items(self, phase: str) -> list[dict]:
        items = self.data.get("phase_items", [])
        if not isinstance(items, list):
            return []
        return [
            i for i in items
            if isinstance(i, dict) and i.get("phase") == phase and self._is_valid_item(i)
        ]

    def _is_valid_item(self, item: dict) -> bool:
        if item.get("cost") not in (None, ""):
            return True
        return all(item.get(k) not in (None, "") for k in ("person", "times", "days", "rate"))

    def _has_phase_input(self, phase: str) -> bool:
        if self._phase_items(phase):
            return True
        if f"{phase}_cost" in self.data:
            return True
        if phase == "service" and "support_cost" in self.data:
            return True
        phase_fields = (f"{phase}_person", f"{phase}_times", f"{phase}_days", f"{phase}_rate")
        if all(k in self.data for k in phase_fields):
            return True
        if phase == "implement" and all(k in self.data for k in ("person", "times", "days", "rate")):
            return True
        return False

    def is_complete(self) -> bool:
        return len(self.missing_required()) == 0

    def add_history(self, role: str, content: str):
        self.history.append({"role": role, "content": content})

    def calculate(self) -> dict:
        d = self.data
        markup  = float(d.get("markup_pct", 0)) / 100

        travel_per_unit = sum([
            float(d.get("fuel", 0)),
            float(d.get("hotel", 0)),
            float(d.get("allowance", 0)),
            float(d.get("flight", 0)),
            float(d.get("rental", 0)),
            float(d.get("taxi", 0)),
            float(d.get("travel_allow", 0)),
        ])

        phase_costs = []
        total_manday = 0
        for key, label in self.PHASES.items():
            items = self._calculated_items(key)
            manday = sum(i["manday"] for i in items)
            calculated_cost = sum(i["cost"] for i in items)
            override_cost = d.get(f"{key}_cost")
            if key == "service":
                override_cost = d.get("service_cost", d.get("support_cost", override_cost))
            cost = float(override_cost) if override_cost not in (None, "") else calculated_cost
            total_manday += manday
            phase_costs.append({
                "key": key,
                "label": label,
                "person": sum(i["person"] for i in items),
                "times": sum(i["times"] for i in items),
                "days": sum(i["days"] for i in items),
                "rate": round((calculated_cost / manday) if manday else 0, 2),
                "manday": manday,
                "cost": round(cost),
                "items": items,
            })

        prepare_cost = phase_costs[0]["cost"]
        implement_cost = phase_costs[1]["cost"]
        service_cost = phase_costs[2]["cost"]
        subtotal_cost    = prepare_cost + implement_cost + service_cost
        profit           = subtotal_cost * markup
        total            = subtotal_cost + profit
        service_pct      = (service_cost / subtotal_cost * 100) if subtotal_cost > 0 else 0
        travel_cost      = travel_per_unit * total_manday

        return {
            "requester_name": d.get("requester_name", "—"),
            "project_name":   d.get("project_name", "—"),
            "person":         phase_costs[1]["person"],
            "times":          phase_costs[1]["times"],
            "days":           phase_costs[1]["days"],
            "rate":           phase_costs[1]["rate"],
            "markup_pct":     d.get("markup_pct", 0),
            "manday":         total_manday,
            "base_cost":      round(subtotal_cost),
            "travel_cost":    round(travel_cost),
            "prepare_cost":   round(prepare_cost),
            "impl_cost":      round(implement_cost),
            "implement_cost": round(implement_cost),
            "service_cost":   round(service_cost),
            "support_cost":   round(service_cost),
            "subtotal_cost":  round(subtotal_cost),
            "profit":         round(profit),
            "sale_price":     round(total),
            "impl_sale":      round(total),
            "supp_pct":       round(service_pct, 2),
            "total":          round(total),
            "phase_costs":    phase_costs,
            "travel_detail": {
                "fuel":         float(d.get("fuel", 0)),
                "hotel":        float(d.get("hotel", 0)),
                "allowance":    float(d.get("allowance", 0)),
                "flight":       float(d.get("flight", 0)),
                "rental":       float(d.get("rental", 0)),
                "taxi":         float(d.get("taxi", 0)),
                "travel_allow": float(d.get("travel_allow", 0)),
            }
        }

    def _calculated_items(self, phase: str) -> list[dict]:
        items = self._phase_items(phase)
        if not items:
            d = self.data
            person = float(d.get(f"{phase}_person", d.get("person", 0) if phase == "implement" else 0))
            times = float(d.get(f"{phase}_times", d.get("times", 1) if phase == "implement" else 1))
            days = float(d.get(f"{phase}_days", d.get("days", 1) if phase == "implement" else 1))
            rate = float(d.get(f"{phase}_rate", d.get("rate", 0) if phase == "implement" else 0))
            items = [{
                "phase": phase,
                "title": self.PHASES[phase],
                "person": person,
                "times": times,
                "days": days,
                "rate": rate,
            }]

        calculated = []
        for i, item in enumerate(items, 1):
            person = float(item.get("person", 0) or 0)
            times = float(item.get("times", 1) or 1)
            days = float(item.get("days", 1) or 1)
            rate = float(item.get("rate", 0) or 0)
            manday = person * times * days
            cost = item.get("cost")
            cost = float(cost) if cost not in (None, "") else manday * rate
            calculated.append({
                "phase": phase,
                "title": item.get("title") or f"{self.PHASES[phase]} item {i}",
                "person": person,
                "times": times,
                "days": days,
                "rate": rate,
                "manday": manday,
                "cost": round(cost),
            })
        return calculated


# ── API schemas ───────────────────────────────────────────────

class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    reply: str
    state_summary: dict
    is_complete: bool
    result: Optional[dict] = None
