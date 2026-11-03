from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from grok_client import plan_from_question, schedule_from_image, xai_key
from transloc import get_arrivals, live_feed

load_dotenv(Path(__file__).parent / ".env")

app = FastAPI(title="Stinger Assistant")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class MoveRequest(BaseModel):
    question: str
    previous_plan: dict | None = None


@app.get("/health")
def health():
    feed = live_feed()
    return {
        "ok": True,
        "xai_key_present": bool(xai_key()),
        "using_recent_data": feed["using_recent_data"],
        "live_vehicles": len(feed.get("vehicles") or []),
    }


@app.post("/move")
def whats_my_move(req: MoveRequest):
    q = (req.question or "").strip()
    if not q:
        raise HTTPException(400, "question is required")
    if req.previous_plan:
        q = (
            f"{q}\n\nThis is a re-check. Previous plan was: {req.previous_plan}. "
            "Highlight anything that changed in reasoning."
        )
    try:
        return plan_from_question(q)
    except RuntimeError as e:
        raise HTTPException(500, str(e)) from e
    except Exception as e:
        raise HTTPException(502, f"Grok/TransLoc error: {e}") from e


@app.get("/arrivals")
def arrivals(stop: str):
    return get_arrivals(stop)


@app.post("/schedule")
async def schedule(file: UploadFile = File(...)):
    raw = await file.read()
    import base64

    b64 = base64.b64encode(raw).decode("ascii")
    mime = file.content_type or "image/png"
    try:
        extracted = schedule_from_image(b64, mime)
    except Exception as e:
        raise HTTPException(502, f"Vision error: {e}") from e
    plans = []
    for cls in (extracted.get("classes") or [])[:6]:
        exam = " This is an exam or quiz." if cls.get("is_exam_or_quiz") else ""
        q = (
            f"I have {cls.get('name')} at {cls.get('building')} at {cls.get('start_time')}.{exam} "
            "What's my move?"
        )
        plans.append({"class": cls, "plan": plan_from_question(q)})
    return {"classes": extracted.get("classes"), "day_plan": plans}
