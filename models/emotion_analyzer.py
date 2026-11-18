"""
ClassVisionAI — Emotion Analyzer
Uses DeepFace with lightweight backend (opencv) for real-time emotion
recognition. Results are cached per track_id to avoid per-frame overhead.
"""

import time
import numpy as np
import cv2
from dataclasses import dataclass, field
from typing import Optional
from loguru import logger
from configs.config import config


EMOTIONS = ["angry", "disgust", "fear", "happy", "sad", "surprise", "neutral"]
POSITIVE_EMOTIONS = {"happy", "surprise", "neutral"}
NEGATIVE_EMOTIONS = {"sad", "angry", "disgust", "fear"}


@dataclass
class EmotionResult:
    dominant_emotion: str
    scores: dict[str, float]      # {emotion: 0-1 probability}
    valence: float                 # -1 to +1 (negative → positive)
    timestamp: float = field(default_factory=time.time)

    @property
    def age_seconds(self) -> float:
        return time.time() - self.timestamp


class EmotionAnalyzer:
    """
    Analyzes facial emotion from cropped face crops.
    Implements per-student caching to respect EMOTION_UPDATE_INTERVAL.
    """

    def __init__(self):
        self.backend = config.EMOTION_BACKEND
        self.update_interval = config.EMOTION_UPDATE_INTERVAL
        self._cache: dict[int, EmotionResult] = {}   # track_id → result
        self._deepface = None
        self._load_deepface()

    def _load_deepface(self):
        """Lazy import DeepFace to avoid startup lag."""
        try:
            from deepface import DeepFace
            self._deepface = DeepFace
            logger.info(f"DeepFace loaded (backend: {self.backend})")
        except Exception as e:
            logger.warning(f"DeepFace not available — emotion analysis disabled. ({e})")

    def analyze(
        self,
        face_crop: np.ndarray,
        track_id: int,
    ) -> Optional[EmotionResult]:
        """
        Analyze emotion for a face crop (BGR numpy array).
        Returns cached result if within update interval.
        Returns None if analysis fails or DeepFace unavailable.
        """
        if self._deepface is None:
            return None

        # Return cached result if still fresh
        cached = self._cache.get(track_id)
        if cached and cached.age_seconds < self.update_interval:
            return cached

        if face_crop is None or face_crop.size == 0:
            return None

        # Resize to 224×224 for speed (DeepFace models trained on this size)
        face_resized = cv2.resize(face_crop, (224, 224))

        try:
            analysis = self._deepface.analyze(
                face_resized,
                actions=["emotion"],
                detector_backend="skip",    # we already have the face crop
                enforce_detection=False,
                silent=True,
            )
            if isinstance(analysis, list):
                analysis = analysis[0]

            raw_scores = analysis.get("emotion", {})

            # Normalize to 0-1
            total = sum(raw_scores.values()) or 1.0
            scores = {k: v / total for k, v in raw_scores.items()}

            dominant = max(scores, key=scores.get)
            valence = self._compute_valence(scores)

            result = EmotionResult(
                dominant_emotion=dominant,
                scores=scores,
                valence=valence,
            )
            self._cache[track_id] = result
            return result

        except Exception as e:
            logger.debug(f"Emotion analysis failed for track {track_id}: {e}")
            return self._cache.get(track_id)  # return stale cache if available

    def _compute_valence(self, scores: dict[str, float]) -> float:
        """
        Compute emotion valence score from -1 (very negative) to +1 (positive).
        Positive: happy, surprise, neutral
        Negative: sad, angry, disgust, fear
        """
        positive = scores.get("happy", 0) + 0.5 * scores.get("surprise", 0) + 0.3 * scores.get("neutral", 0)
        negative = (
            scores.get("sad", 0)
            + scores.get("angry", 0)
            + scores.get("disgust", 0)
            + 0.7 * scores.get("fear", 0)
        )
        raw = positive - negative
        return max(-1.0, min(1.0, raw))

    def emotion_to_attention_weight(self, emotion_result: Optional[EmotionResult]) -> float:
        """
        Convert emotion valence to 0-1 weight for attention score computation.
        Neutral/positive → weight toward 1.0
        Negative emotions → weight toward 0.4 (still somewhat attentive but not engaged)
        """
        if emotion_result is None:
            return 0.5  # neutral default
        # Map valence [-1, +1] → [0.2, 1.0]
        return 0.2 + 0.8 * (emotion_result.valence + 1) / 2

    def clear_stale(self, active_track_ids: set[int]):
        """Remove cache entries for tracks no longer in frame."""
        stale = set(self._cache.keys()) - active_track_ids
        for tid in stale:
            del self._cache[tid]
