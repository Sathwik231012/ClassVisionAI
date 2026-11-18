"""
ClassVisionAI — Attention Score Engine
Combines head pose, behaviour, and emotion signals into a 0–100 attention score.
Maintains per-student rolling history for smooth, stable scoring.
"""

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional
from configs.config import config
from models.behaviour_classifier import BehaviourState


@dataclass
class StudentState:
    """All current metrics for one tracked student."""
    track_id: int
    # Head pose
    yaw: float = 0.0
    pitch: float = 0.0
    roll: float = 0.0
    is_attentive_hp: bool = True      # head-pose based
    # Behaviour
    behaviour: BehaviourState = BehaviourState.UNKNOWN
    behaviour_confidence: float = 0.5
    behaviour_weight: float = 0.5
    # Emotion
    dominant_emotion: Optional[str] = None
    emotion_valence: float = 0.0      # -1 to +1
    emotion_weight: float = 0.5       # 0 to 1
    # Composite
    attention_score: float = 50.0     # 0 to 100
    # Bounding box (xyxy, pixel coords)
    bbox: tuple = (0, 0, 0, 0)
    last_seen: float = field(default_factory=time.time)


class AttentionScoreEngine:
    """
    Maintains rolling attention history for each student and
    computes composite attention score every SCORE_UPDATE_INTERVAL seconds.

    Weights (from config):
        head_pose  = 0.45
        behaviour  = 0.35
        emotion    = 0.20
    """

    def __init__(self):
        self.hp_weight  = config.HEAD_POSE_WEIGHT
        self.beh_weight = config.BEHAVIOUR_WEIGHT
        self.emo_weight = config.EMOTION_WEIGHT
        self.window     = config.ATTENTION_WINDOW_SECONDS
        self.interval   = config.SCORE_UPDATE_INTERVAL

        # track_id → deque of (timestamp, raw_score) tuples
        self._history: dict[int, deque] = {}
        self._last_scores: dict[int, float] = {}
        self._last_update: dict[int, float] = {}

    def update(self, state: StudentState) -> float:
        """
        Update attention score for a student given current state.
        Returns the new 0–100 attention score.
        """
        tid = state.track_id
        now = time.time()

        # Throttle — only recompute every SCORE_UPDATE_INTERVAL seconds
        if tid in self._last_update:
            if now - self._last_update[tid] < self.interval:
                return self._last_scores.get(tid, 50.0)

        # ── Component scores (all 0–1) ────────────────────────────────────
        head_pose_score = 1.0 if state.is_attentive_hp else self._soft_hp_score(state)
        behaviour_score = state.behaviour_weight         # already 0-1
        emotion_score   = state.emotion_weight           # already 0-1

        # ── Weighted composite ────────────────────────────────────────────
        composite = (
            self.hp_weight  * head_pose_score
            + self.beh_weight * behaviour_score
            + self.emo_weight * emotion_score
        )
        # Scale to 0–100
        raw_score = composite * 100.0

        # ── Rolling history ───────────────────────────────────────────────
        if tid not in self._history:
            self._history[tid] = deque()

        hist = self._history[tid]
        hist.append((now, raw_score))

        # Remove entries older than window
        while hist and now - hist[0][0] > self.window:
            hist.popleft()

        # Smooth score: exponential moving average over history
        if hist:
            scores = [s for _, s in hist]
            smoothed = self._ema(scores, alpha=0.3)
        else:
            smoothed = raw_score

        final = round(max(0.0, min(100.0, smoothed)), 1)
        self._last_scores[tid] = final
        self._last_update[tid] = now
        state.attention_score  = final
        return final

    def get_class_average(self, active_track_ids: set[int]) -> float:
        """Compute real-time class-average attention score."""
        scores = [
            self._last_scores[tid]
            for tid in active_track_ids
            if tid in self._last_scores
        ]
        return round(sum(scores) / len(scores), 1) if scores else 0.0

    def purge_stale(self, active_track_ids: set[int]):
        """Remove history for students no longer in frame."""
        stale = set(self._history.keys()) - active_track_ids
        for tid in stale:
            self._history.pop(tid, None)
            self._last_scores.pop(tid, None)
            self._last_update.pop(tid, None)

    @staticmethod
    def _soft_hp_score(state: StudentState) -> float:
        """
        Soft head pose score when not classified as attentive.
        Larger deviation = lower score, but not binary zero.
        """
        yaw_excess   = max(0, abs(state.yaw)   - config.YAW_THRESHOLD)
        pitch_excess = max(0, abs(state.pitch) - config.PITCH_THRESHOLD)
        penalty = (yaw_excess * 0.012) + (pitch_excess * 0.018)
        return max(0.0, 1.0 - penalty)

    @staticmethod
    def _ema(values: list[float], alpha: float = 0.3) -> float:
        """Exponential moving average (most recent = highest weight)."""
        if not values:
            return 0.0
        ema = values[0]
        for v in values[1:]:
            ema = alpha * v + (1 - alpha) * ema
        return ema

    def score_label(self, score: float) -> str:
        """Human-readable attention level."""
        if score >= 80: return "Highly Attentive"
        if score >= 60: return "Attentive"
        if score >= 40: return "Partially Attentive"
        if score >= 20: return "Distracted"
        return "Not Attentive"

    def score_color(self, score: float) -> str:
        """Hex color for attention score (green → red)."""
        if score >= 80: return "#22c55e"
        if score >= 60: return "#84cc16"
        if score >= 40: return "#f59e0b"
        if score >= 20: return "#f97316"
        return "#ef4444"
