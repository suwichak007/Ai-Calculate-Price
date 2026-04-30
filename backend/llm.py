"""
llm.py — LLM integration via Groq API
"""

import json
import re
import os
from groq import Groq


def load_llm():
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError("ไม่พบ GROQ_API_KEY ใน environment variables")
    return Groq(api_key=api_key)


def call_llm(client, messages: list) -> str:
    res = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        max_tokens=1000,
        temperature=0.1,
    )
    return res.choices[0].message.content.strip()


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