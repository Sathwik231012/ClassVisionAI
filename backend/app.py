"""
ClassVisionAI — FastAPI Application
Provides:
  - REST endpoints for session management and analytics
  - WebSocket for real-time frame metrics streaming
  - MJPEG video stream endpoint for live annotated feed
"""

import cv2
import time
import asyncio
import json
import base64
from datetime import datetime
from typing import Optional, AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from loguru import logger
from pydantic import BaseModel

from configs.config import config
from backend.database import init_db, get_db, AsyncSessionLocal, ClassSession, StudentSnapshot, BehaviourEvent, Alert, TimetableEntry
from backend.pipeline import ClassroomPipeline
from backend.analytics import get_session_analytics, get_current_analytics
from backend.break_advisor import BreakAdvisor


# ─── Pydantic Models ──────────────────────────────────────────────────────────
class TimetableEntryCreate(BaseModel):
    day_of_week: int
    start_time: str
    end_time: str
    subject: str = ""
    instructor: str = ""
    classroom: str = ""
    color_hex: str = "#3B82F6"


class TimetableEntryUpdate(BaseModel):
    day_of_week: int = None
    start_time: str = None
    end_time: str = None
    subject: str = None
    instructor: str = None
    classroom: str = None
    color_hex: str = None


# ─── Global pipeline state ───────────────────────────────────────────────────
_pipeline: Optional[ClassroomPipeline] = None
_camera: Optional[cv2.VideoCapture] = None
_current_session_id: Optional[int] = None
_ws_clients: set[WebSocket] = set()
_latest_data: dict = {}
_break_advisor: Optional[BreakAdvisor] = None
_last_break_check: float = 0
_last_snapshot_save: float = 0


# ─── Lifespan ─────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    logger.info("ClassVisionAI backend started.")
    yield
    _stop_camera()
    logger.info("ClassVisionAI backend shut down.")


app = FastAPI(
    title="ClassVisionAI",
    description="Smart Classroom Monitoring System",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve frontend
import os
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")


# ─── Camera helpers ───────────────────────────────────────────────────────────
def _start_camera() -> bool:
    global _camera
    if _camera and _camera.isOpened():
        return True
    cap = cv2.VideoCapture(config.CAMERA_INDEX)
    if not cap.isOpened():
        logger.error(f"Cannot open camera index {config.CAMERA_INDEX}")
        return False
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.FRAME_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, config.TARGET_FPS)
    _camera = cap
    return True


async def _save_snapshots(session_id: int, data: dict):
    """Write one snapshot row per tracked student (used by session analytics)."""
    students = data.get("students", [])
    if not session_id or not students:
        return
    try:
        async with AsyncSessionLocal() as db:
            for s in students:
                db.add(StudentSnapshot(
                    session_id=session_id,
                    track_id=s.get("track_id"),
                    yaw=s.get("yaw"),
                    pitch=s.get("pitch"),
                    is_attentive=s.get("is_attentive"),
                    attention_score=s.get("attention_score"),
                    dominant_emotion=s.get("dominant_emotion"),
                    behaviour_state=s.get("behaviour"),
                ))
            await db.commit()
    except Exception as e:
        logger.error(f"Failed to save student snapshots: {e}")


def _stop_camera():
    global _camera, _pipeline
    if _camera:
        _camera.release()
        _camera = None
    if _pipeline:
        _pipeline.release()
        _pipeline = None


# ─── Background frame processor ───────────────────────────────────────────────
async def _frame_loop():
    """Background task: reads camera, runs pipeline, broadcasts to WS clients."""
    global _latest_data, _ws_clients, _last_break_check, _last_snapshot_save
    logger.info("Frame loop started.")
    frame_interval = 1.0 / config.TARGET_FPS

    while _pipeline and _camera and _camera.isOpened():
        t0 = time.time()
        ret, frame = _camera.read()
        if not ret:
            await asyncio.sleep(0.05)
            continue

        # Run pipeline in executor to avoid blocking event loop
        loop = asyncio.get_event_loop()
        annotated, data = await loop.run_in_executor(
            None, _pipeline.process_frame, frame
        )
        _latest_data = data

        # Save student snapshots every SCORE_UPDATE_INTERVAL seconds
        if (time.time() - _last_snapshot_save) >= config.SCORE_UPDATE_INTERVAL:
            _last_snapshot_save = time.time()
            await _save_snapshots(_current_session_id, data)

        # Check for break recommendation every 30 seconds
        if _break_advisor and (time.time() - _last_break_check) >= 30:
            _last_break_check = time.time()
            recommendation = _break_advisor.recommend_break(_latest_data)
            if recommendation:
                _latest_data['break_recommendation'] = {
                    'should_break': recommendation.should_break,
                    'reason': recommendation.reason,
                    'suggested_duration': recommendation.suggested_duration_minutes,
                    'urgency': recommendation.urgency,
                    'time_since_last_break': recommendation.time_since_last_break
                }

        # Encode annotated frame to JPEG for streaming
        _, jpeg_buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 75])
        frame_b64 = base64.b64encode(jpeg_buf.tobytes()).decode("utf-8")
        data["frame_b64"] = frame_b64

        # Broadcast to all WebSocket clients
        if _ws_clients:
            msg = json.dumps(data)
            dead = set()
            for ws in list(_ws_clients):
                try:
                    await ws.send_text(msg)
                except Exception:
                    dead.add(ws)
            _ws_clients -= dead

        # Maintain target FPS
        elapsed = time.time() - t0
        sleep_time = max(0, frame_interval - elapsed)
        await asyncio.sleep(sleep_time)

    logger.info("Frame loop ended.")


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    login_path = os.path.join(frontend_dir, "login.html")
    if os.path.exists(login_path):
        with open(login_path) as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h1>ClassVisionAI API Running</h1><p>Frontend not found.</p>")


@app.get("/app", response_class=HTMLResponse)
async def app_page():
    index_path = os.path.join(frontend_dir, "index.html")
    if os.path.exists(index_path):
        with open(index_path) as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h1>ClassVisionAI</h1><p>Application not found.</p>")


@app.post("/api/session/start")
async def start_session(
    session_name: str = "Classroom Session",
    subject: str = "",
    instructor: str = "",
    db: AsyncSession = Depends(get_db),
):
    global _pipeline, _current_session_id, _break_advisor, _last_break_check, _last_snapshot_save

    if _pipeline and _pipeline.is_running:
        raise HTTPException(400, "A session is already running.")

    if not _start_camera():
        raise HTTPException(500, "Failed to open camera.")

    # Create DB session record
    session = ClassSession(
        session_name=session_name,
        subject=subject,
        instructor=instructor,
        started_at=datetime.utcnow(),
        is_active=True,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    _current_session_id = session.id

    # Start pipeline
    _pipeline = ClassroomPipeline(session_id=session.id)
    _pipeline.is_running = True

    # Start break advisor
    _break_advisor = BreakAdvisor()
    _break_advisor.start_session()
    _last_break_check = time.time()
    _last_snapshot_save = 0

    # Launch background frame loop
    asyncio.create_task(_frame_loop())

    return {"status": "started", "session_id": session.id, "message": f"Session '{session_name}' started."}


@app.post("/api/session/stop")
async def stop_session(db: AsyncSession = Depends(get_db)):
    global _pipeline, _camera, _current_session_id, _break_advisor

    if not _pipeline:
        raise HTTPException(400, "No active session.")

    # Save the final state so short sessions also have analytics
    await _save_snapshots(_current_session_id, _latest_data)

    # Update DB record
    result = await db.execute(
        select(ClassSession).where(ClassSession.id == _current_session_id)
    )
    session = result.scalar_one_or_none()
    if session:
        session.ended_at = datetime.utcnow()
        session.is_active = False
        if _pipeline:
            session.avg_attention_score = _latest_data.get("class_attention", 0)
            session.total_students_detected = _latest_data.get("student_count", 0)
        await db.commit()

    _stop_camera()
    _current_session_id = None
    _break_advisor = None

    return {"status": "stopped", "message": "Session ended successfully."}


@app.get("/api/session/status")
async def session_status():
    return {
        "is_running": _pipeline is not None and _pipeline.is_running,
        "session_id": _current_session_id,
        "data": _latest_data,
    }


@app.get("/api/sessions")
async def list_sessions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ClassSession).order_by(desc(ClassSession.started_at)).limit(20)
    )
    sessions = result.scalars().all()
    return [
        {
            "id": s.id,
            "session_name": s.session_name,
            "subject": s.subject,
            "instructor": s.instructor,
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "ended_at": s.ended_at.isoformat() if s.ended_at else None,
            "is_active": s.is_active,
            "avg_attention_score": s.avg_attention_score,
            "total_students_detected": s.total_students_detected,
        }
        for s in sessions
    ]


@app.get("/api/metrics/live")
async def live_metrics():
    return JSONResponse(_latest_data)


@app.get("/api/stream/video")
async def video_stream():
    """MJPEG stream of annotated classroom feed."""
    async def generate():
        while _camera and _camera.isOpened() and _pipeline:
            if "frame_b64" in _latest_data:
                frame_bytes = base64.b64decode(_latest_data["frame_b64"])
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + frame_bytes
                    + b"\r\n"
                )
            await asyncio.sleep(1.0 / config.TARGET_FPS)

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.websocket("/ws/metrics")
async def ws_metrics(websocket: WebSocket):
    """WebSocket — streams real-time metrics JSON to connected clients."""
    await websocket.accept()
    _ws_clients.add(websocket)
    logger.info(f"WebSocket client connected. Total: {len(_ws_clients)}")
    try:
        while True:
            # Keep connection alive by receiving pings
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _ws_clients.discard(websocket)
        logger.info(f"WebSocket client disconnected. Total: {len(_ws_clients)}")


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "device": config.get_device(),
        "camera_open": _camera is not None and _camera.isOpened() if _camera else False,
        "pipeline_active": _pipeline is not None,
    }


@app.get("/api/analytics/session/{session_id}")
async def get_analytics(session_id: int, db: AsyncSession = Depends(get_db)):
    """Get analytics for a specific session."""
    try:
        analytics = await get_session_analytics(session_id, db)
        return analytics
    except Exception as e:
        logger.error(f"Error getting analytics for session {session_id}: {e}")
        raise HTTPException(500, f"Failed to get analytics: {str(e)}")


@app.get("/api/analytics/current")
async def get_current_analytics_endpoint():
    """Get analytics for currently active session."""
    if not _pipeline or not _current_session_id:
        # Return empty analytics
        return {
            "attention_distribution": {"0-20": 0, "21-40": 0, "41-60": 0, "61-80": 0, "81-100": 0},
            "attention_timeline": [],
            "behaviour_timeline": [],
            "emotion_summary": {},
            "peak_attention": 0,
            "lowest_attention": 0,
            "avg_attention": 0,
        }
    
    # Use in-memory latest data
    analytics = get_current_analytics(_latest_data, [])
    return analytics


# ─── Timetable Endpoints ──────────────────────────────────────────────────────

@app.post("/api/timetable")
async def create_timetable_entry(
    entry_data: TimetableEntryCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new timetable entry"""
    entry = TimetableEntry(
        day_of_week=entry_data.day_of_week,
        start_time=entry_data.start_time,
        end_time=entry_data.end_time,
        subject=entry_data.subject,
        instructor=entry_data.instructor,
        classroom=entry_data.classroom,
        color_hex=entry_data.color_hex,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return {"id": entry.id, "message": "Timetable entry created"}


@app.get("/api/timetable")
async def list_timetable(db: AsyncSession = Depends(get_db)):
    """List all timetable entries"""
    result = await db.execute(
        select(TimetableEntry).where(TimetableEntry.is_active == True).order_by(TimetableEntry.day_of_week, TimetableEntry.start_time)
    )
    entries = result.scalars().all()
    return [
        {
            "id": e.id,
            "day_of_week": e.day_of_week,
            "start_time": e.start_time,
            "end_time": e.end_time,
            "subject": e.subject,
            "instructor": e.instructor,
            "classroom": e.classroom,
            "color_hex": e.color_hex,
        }
        for e in entries
    ]


@app.put("/api/timetable/{entry_id}")
async def update_timetable_entry(
    entry_id: int,
    entry_data: TimetableEntryUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a timetable entry"""
    result = await db.execute(select(TimetableEntry).where(TimetableEntry.id == entry_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(404, "Entry not found")
    
    if entry_data.day_of_week is not None: entry.day_of_week = entry_data.day_of_week
    if entry_data.start_time: entry.start_time = entry_data.start_time
    if entry_data.end_time: entry.end_time = entry_data.end_time
    if entry_data.subject: entry.subject = entry_data.subject
    if entry_data.instructor: entry.instructor = entry_data.instructor
    if entry_data.classroom: entry.classroom = entry_data.classroom
    if entry_data.color_hex: entry.color_hex = entry_data.color_hex
    
    await db.commit()
    return {"message": "Entry updated"}


@app.delete("/api/timetable/{entry_id}")
async def delete_timetable_entry(entry_id: int, db: AsyncSession = Depends(get_db)):
    """Delete (soft delete) a timetable entry"""
    result = await db.execute(select(TimetableEntry).where(TimetableEntry.id == entry_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(404, "Entry not found")
    
    entry.is_active = False
    await db.commit()
    return {"message": "Entry deleted"}


@app.get("/api/timetable/now")
async def get_current_timetable_entry(db: AsyncSession = Depends(get_db)):
    """Get the timetable entry matching current day and time"""
    now = datetime.now()
    current_day = now.weekday()  # 0=Monday
    current_time = now.strftime("%H:%M")
    
    result = await db.execute(
        select(TimetableEntry).where(
            TimetableEntry.day_of_week == current_day,
            TimetableEntry.is_active == True
        )
    )
    entries = result.scalars().all()
    
    # Find entry where current_time is between start_time and end_time
    for entry in entries:
        if entry.start_time <= current_time <= entry.end_time:
            return {
                "id": entry.id,
                "subject": entry.subject,
                "instructor": entry.instructor,
                "classroom": entry.classroom,
                "start_time": entry.start_time,
                "end_time": entry.end_time,
            }
    
    return {"message": "No class scheduled now"}


@app.post("/api/break/acknowledge")
async def acknowledge_break(duration_minutes: int = 5):
    """Acknowledge a break and reset break timer"""
    if _break_advisor:
        _break_advisor.acknowledge_break(duration_minutes)
        return {"message": "Break acknowledged"}
    raise HTTPException(400, "No active session")
