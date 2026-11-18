"""
ClassVisionAI — Database Models
SQLAlchemy async models for session, student, and event tracking.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column, Integer, Float, String, Boolean, DateTime, ForeignKey, Text, JSON
)
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.ext.asyncio import async_sessionmaker
from configs.config import config


# ─── Base ─────────────────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ─── Models ───────────────────────────────────────────────────────────────────

class ClassSession(Base):
    """A single classroom monitoring session."""
    __tablename__ = "class_sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_name = Column(String(200), nullable=True)
    subject = Column(String(100), nullable=True)
    instructor = Column(String(100), nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    total_students_detected = Column(Integer, default=0)
    avg_attention_score = Column(Float, default=0.0)

    # Relationships
    student_snapshots = relationship("StudentSnapshot", back_populates="session")
    behaviour_events = relationship("BehaviourEvent", back_populates="session")
    alerts = relationship("Alert", back_populates="session")


class StudentSnapshot(Base):
    """
    Per-student metric snapshot — written every SCORE_UPDATE_INTERVAL seconds.
    Uses track_id (DeepSORT) as the student identifier within a session.
    No PII stored — only derived features.
    """
    __tablename__ = "student_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("class_sessions.id"), index=True)
    track_id = Column(Integer, index=True)        # DeepSORT track ID
    timestamp = Column(DateTime, default=datetime.utcnow)

    # ── Head Pose ──────────────────────────────────────────────────────────
    yaw = Column(Float, nullable=True)             # degrees, + = right
    pitch = Column(Float, nullable=True)           # degrees, + = down
    roll = Column(Float, nullable=True)            # degrees

    # ── Attention ──────────────────────────────────────────────────────────
    is_attentive = Column(Boolean, nullable=True)  # head-pose attention
    attention_score = Column(Float, nullable=True) # 0–100 composite

    # ── Emotion ────────────────────────────────────────────────────────────
    dominant_emotion = Column(String(20), nullable=True)
    emotion_scores = Column(JSON, nullable=True)   # {emotion: probability}

    # ── Behaviour ──────────────────────────────────────────────────────────
    behaviour_state = Column(String(40), nullable=True)
    # attentive | head_down | phone_usage | raised_hand | side_talk | unknown

    # Relationship
    session = relationship("ClassSession", back_populates="student_snapshots")


class BehaviourEvent(Base):
    """Discrete timestamped behaviour event for a student."""
    __tablename__ = "behaviour_events"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("class_sessions.id"), index=True)
    track_id = Column(Integer)
    timestamp = Column(DateTime, default=datetime.utcnow)
    event_type = Column(String(40))    # phone_detected | head_down | raised_hand | side_talk
    confidence = Column(Float)
    duration_seconds = Column(Float, nullable=True)

    session = relationship("ClassSession", back_populates="behaviour_events")


class Alert(Base):
    """Class-level or student-level alert."""
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("class_sessions.id"), index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    alert_type = Column(String(50))    # low_attention | mass_distraction | etc.
    message = Column(Text)
    avg_attention_at_alert = Column(Float, nullable=True)
    acknowledged = Column(Boolean, default=False)

    session = relationship("ClassSession", back_populates="alerts")


class TimetableEntry(Base):
    """Weekly timetable entry for classroom scheduling."""
    __tablename__ = "timetable_entries"

    id = Column(Integer, primary_key=True, index=True)
    day_of_week = Column(Integer, nullable=False)  # 0=Monday, 6=Sunday
    start_time = Column(String(5), nullable=False)  # HH:MM format
    end_time = Column(String(5), nullable=False)
    subject = Column(String(100))
    instructor = Column(String(100))
    classroom = Column(String(50))
    color_hex = Column(String(7), default="#3B82F6")  # For UI display
    is_active = Column(Boolean, default=True)


# ─── Engine & Session factory ─────────────────────────────────────────────────
engine = create_async_engine(
    config.DATABASE_URL,
    echo=False,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db():
    """Create all tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    """FastAPI dependency: yields an async DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
