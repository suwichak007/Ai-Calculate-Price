"""
main.py — Entry point
  - สร้าง FastAPI app
  - โหลด LLM ตอน startup
  - mount router

Usage:
  pip install fastapi uvicorn llama-cpp-python openpyxl reportlab
  python main.py
  # หรือ
  uvicorn main:app --host 0.0.0.0 --port 8070 --reload
"""

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from manday_chatbot.llm import load_llm
from manday_chatbot.router import router, set_llm

# ── App ───────────────────────────────────────────────────────

app = FastAPI(title="Manday Cost Chatbot API", version="1.2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.mount("/static", StaticFiles(directory="static"), name="static")

# ── Startup: โหลด LLM ครั้งเดียว ──────────────────────────────

@app.on_event("startup")
async def startup_event():
    llm = load_llm()
    set_llm(llm)


# ── Run ───────────────────────────────────────────────────────

if __name__ == "__main__":
    PORT = 8070
    print("\n" + "="*50)
    print(f"  Manday Cost Chatbot v1.2")
    print(f"  http://localhost:{PORT}")
    print("="*50 + "\n")
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=True)