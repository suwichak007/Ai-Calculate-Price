import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv  # ← เพิ่ม

load_dotenv()                   # ← เพิ่ม (โหลด .env ก่อนทุกอย่าง)

from llm import load_llm
from router import router, set_llm

app = FastAPI(title="Manday Cost Chatbot API", version="1.2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

@app.on_event("startup")
async def startup_event():
    llm = load_llm()
    set_llm(llm)

if __name__ == "__main__":
    PORT = 8060
    print("\n" + "="*50)
    print(f"  Manday Cost Chatbot v1.2")
    print(f"  http://localhost:{PORT}")
    print("="*50 + "\n")
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False) 