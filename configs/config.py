"""
ClassVisionAI — Configuration
Loads settings from .env with sensible defaults for Apple Silicon Macs.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env if present
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv(Path(__file__).parent.parent / ".env.example")


class Config:
    # ── Server ──────────────────────────────────────────────────────────────
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", 8000))
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"

    # ── Camera ──────────────────────────────────────────────────────────────
    CAMERA_INDEX: int = int(os.getenv("CAMERA_INDEX", 0))
    FRAME_WIDTH: int = int(os.getenv("FRAME_WIDTH", 1280))
    FRAME_HEIGHT: int = int(os.getenv("FRAME_HEIGHT", 720))
    TARGET_FPS: int = int(os.getenv("TARGET_FPS", 15))

    # ── Model ───────────────────────────────────────────────────────────────
    YOLO_MODEL: str = os.getenv("YOLO_MODEL", "yolov8n.pt")
    YOLO_CONFIDENCE: float = float(os.getenv("YOLO_CONFIDENCE", 0.5))
    DEVICE: str = os.getenv("DEVICE", "auto")  # auto-detects mps / cuda / cpu

    # ── Attention ───────────────────────────────────────────────────────────
    HEAD_POSE_WEIGHT: float = float(os.getenv("HEAD_POSE_WEIGHT", 0.45))
    BEHAVIOUR_WEIGHT: float = float(os.getenv("BEHAVIOUR_WEIGHT", 0.35))
    EMOTION_WEIGHT: float = float(os.getenv("EMOTION_WEIGHT", 0.20))
    ATTENTION_WINDOW_SECONDS: int = int(os.getenv("ATTENTION_WINDOW_SECONDS", 60))
    SCORE_UPDATE_INTERVAL: int = int(os.getenv("SCORE_UPDATE_INTERVAL", 10))

    # ── Head Pose ───────────────────────────────────────────────────────────
    YAW_THRESHOLD: float = float(os.getenv("YAW_ATTENTION_THRESHOLD", 25))
    PITCH_THRESHOLD: float = float(os.getenv("PITCH_ATTENTION_THRESHOLD", 20))

    # ── Alerts ──────────────────────────────────────────────────────────────
    LOW_ATTENTION_THRESHOLD: int = int(os.getenv("LOW_ATTENTION_THRESHOLD", 40))
    ALERT_COOLDOWN_SECONDS: int = int(os.getenv("ALERT_COOLDOWN_SECONDS", 60))

    # ── Database ────────────────────────────────────────────────────────────
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", "sqlite+aiosqlite:///./classvision.db"
    )

    # ── Emotion ─────────────────────────────────────────────────────────────
    EMOTION_BACKEND: str = os.getenv("EMOTION_BACKEND", "opencv")
    EMOTION_UPDATE_INTERVAL: int = int(os.getenv("EMOTION_UPDATE_INTERVAL", 3))

    # ── Privacy ─────────────────────────────────────────────────────────────
    STORE_RAW_FRAMES: bool = os.getenv("STORE_RAW_FRAMES", "false").lower() == "true"
    BLUR_FACES_IN_STREAM: bool = (
        os.getenv("BLUR_FACES_IN_STREAM", "false").lower() == "true"
    )

    # ── Derived ─────────────────────────────────────────────────────────────
    @classmethod
    def get_device(cls) -> str:
        """Auto-detect best device if 'auto' specified."""
        if cls.DEVICE == "auto":
            try:
                import torch
                if torch.backends.mps.is_available():
                    return "mps"
                elif torch.cuda.is_available():
                    return "cuda"
                else:
                    return "cpu"
            except ImportError:
                return "cpu"
        return cls.DEVICE


config = Config()
