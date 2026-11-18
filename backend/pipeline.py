"""
ClassVisionAI — Video Processing Pipeline
Orchestrates: YOLOv8 detection → DeepSORT tracking → Head Pose → Emotion → Behaviour → Attention Score

Designed for Apple Silicon (MPS) — auto-falls back to CPU.
"""

import cv2
import time
import numpy as np
import asyncio
from typing import Optional, AsyncGenerator
from loguru import logger
from ultralytics import YOLO
from deep_sort_realtime.deepsort_tracker import DeepSort

from configs.config import config
from models.head_pose import HeadPoseEstimator, HeadPoseResult
from models.emotion_analyzer import EmotionAnalyzer
from models.behaviour_classifier import BehaviourClassifier, BehaviourState
from utils.attention_engine import AttentionScoreEngine, StudentState


# ── Colours for visualization ─────────────────────────────────────────────────
COLOUR_ATTENTIVE    = (34,  197, 94)    # green
COLOUR_DISTRACTED   = (239, 68,  68)    # red
COLOUR_RAISED_HAND  = (59,  130, 246)   # blue
COLOUR_PHONE        = (234, 179, 8)     # yellow
COLOUR_HEAD_DOWN    = (168, 85,  247)   # purple
COLOUR_SIDE_TALK    = (249, 115, 22)    # orange
BEHAVIOUR_COLOURS = {
    BehaviourState.ATTENTIVE:   COLOUR_ATTENTIVE,
    BehaviourState.RAISED_HAND: COLOUR_RAISED_HAND,
    BehaviourState.PHONE_USAGE: COLOUR_PHONE,
    BehaviourState.HEAD_DOWN:   COLOUR_HEAD_DOWN,
    BehaviourState.SIDE_TALK:   COLOUR_SIDE_TALK,
    BehaviourState.UNKNOWN:     (200, 200, 200),
}


class ClassroomPipeline:
    """
    Main processing pipeline. Call process_frame() for each camera frame.
    Thread-safe student state is maintained internally.
    """

    def __init__(self, session_id: Optional[int] = None):
        self.session_id = session_id
        self.device = config.get_device()
        logger.info(f"Pipeline initializing on device: {self.device}")

        # ── Models ──────────────────────────────────────────────────────────
        self.yolo = YOLO(config.YOLO_MODEL)
        self.yolo.to(self.device)

        self.tracker = DeepSort(
            max_age=30,              # frames to keep lost track
            n_init=3,               # frames before confirming new track
            nn_budget=100,
            embedder="mobilenet",   # lightweight re-ID
            half=True,              # FP16 for speed on MPS
            bgr=True,               # OpenCV gives BGR
        )

        self.head_pose   = HeadPoseEstimator(config.FRAME_WIDTH, config.FRAME_HEIGHT)
        self.emotion     = EmotionAnalyzer()
        self.behaviour   = BehaviourClassifier()
        self.attention   = AttentionScoreEngine()

        # ── State ────────────────────────────────────────────────────────────
        self.students: dict[int, StudentState] = {}  # track_id → StudentState
        self.frame_count = 0
        self.fps_actual  = 0.0
        self._t_last     = time.time()
        self.is_running  = False

        # ── Event callbacks ──────────────────────────────────────────────────
        self._frame_callbacks = []    # list of async callables

        logger.info("Pipeline ready.")

    # ─── Main Entry Point ──────────────────────────────────────────────────────

    def process_frame(self, frame_bgr: np.ndarray) -> tuple[np.ndarray, dict]:
        """
        Process one BGR frame. Returns:
          - annotated frame (BGR)
          - data dict with all student metrics + class stats
        """
        self.frame_count += 1
        h, w = frame_bgr.shape[:2]
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

        # ── 1. YOLO Person Detection ──────────────────────────────────────────
        yolo_results = self.yolo.predict(
            frame_bgr,
            classes=[0],                # class 0 = person only
            conf=config.YOLO_CONFIDENCE,
            verbose=False,
            device=self.device,
        )
        raw_detections = []
        for r in yolo_results:
            for box in r.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                conf = float(box.conf[0])
                raw_detections.append(([x1, y1, x2 - x1, y2 - y1], conf, "person"))

        # ── 2. DeepSORT Tracking ──────────────────────────────────────────────
        tracks = self.tracker.update_tracks(raw_detections, frame=frame_bgr)
        active_ids = set()

        # ── 3. Head Pose (whole frame, all faces at once) ─────────────────────
        hp_results: dict[int, HeadPoseResult] = self.head_pose.estimate(frame_rgb)

        for i, track in enumerate(tracks):
            if not track.is_confirmed():
                continue

            tid = track.track_id
            active_ids.add(tid)
            x1, y1, x2, y2 = map(int, track.to_ltrb())
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)

            if x2 <= x1 or y2 <= y1:
                continue

            # Init student state
            if tid not in self.students:
                self.students[tid] = StudentState(track_id=tid)
            student = self.students[tid]
            student.bbox = (x1, y1, x2, y2)
            student.last_seen = time.time()

            # ── Face crop for emotion ─────────────────────────────────────────
            # Use top portion of person bbox for face
            face_h = int((y2 - y1) * 0.40)
            face_crop_bgr = frame_bgr[y1:y1 + face_h, x1:x2]

            # ── Body crop for behaviour ───────────────────────────────────────
            person_crop_rgb = frame_rgb[y1:y2, x1:x2]

            # ── Assign head pose (nearest face landmark centroid to bbox) ─────
            hp = hp_results.get(i)   # face index aligned to track index (approx)
            if hp is None and len(hp_results) > 0:
                hp = next(iter(hp_results.values()))

            if hp:
                student.yaw   = hp.yaw
                student.pitch = hp.pitch
                student.roll  = hp.roll
                student.is_attentive_hp = hp.is_attentive

            # ── Emotion (throttled per student) ───────────────────────────────
            emotion_result = self.emotion.analyze(face_crop_bgr, tid)
            if emotion_result:
                student.dominant_emotion = emotion_result.dominant_emotion
                student.emotion_valence  = emotion_result.valence
                student.emotion_weight   = self.emotion.emotion_to_attention_weight(emotion_result)

            # ── Behaviour ─────────────────────────────────────────────────────
            beh_result = self.behaviour.classify(
                person_crop_rgb,
                yaw=student.yaw,
                pitch=student.pitch,
            )
            student.behaviour            = beh_result.state
            student.behaviour_confidence = beh_result.confidence
            student.behaviour_weight     = beh_result.engagement_weight

            # ── Attention Score ───────────────────────────────────────────────
            self.attention.update(student)

        # ── 4. Purge stale students ────────────────────────────────────────────
        gone = set(self.students.keys()) - active_ids
        for tid in gone:
            del self.students[tid]
        self.attention.purge_stale(active_ids)
        self.emotion.clear_stale(active_ids)

        # ── 5. Annotate frame ─────────────────────────────────────────────────
        annotated = self._annotate(frame_bgr.copy())

        # ── 6. Build data payload ─────────────────────────────────────────────
        class_avg = self.attention.get_class_average(active_ids)
        self._update_fps()

        data = {
            "session_id": self.session_id,
            "frame": self.frame_count,
            "fps": round(self.fps_actual, 1),
            "student_count": len(active_ids),
            "class_attention": class_avg,
            "students": [self._student_to_dict(s) for s in self.students.values()],
            "timestamp": time.time(),
        }

        return annotated, data

    # ─── Helpers ──────────────────────────────────────────────────────────────

    def _annotate(self, frame: np.ndarray) -> np.ndarray:
        """Draw bounding boxes, scores, and behaviour labels on frame."""
        for student in self.students.values():
            x1, y1, x2, y2 = student.bbox
            colour = BEHAVIOUR_COLOURS.get(student.behaviour, (200, 200, 200))
            score  = student.attention_score

            # Bounding box
            cv2.rectangle(frame, (x1, y1), (x2, y2), colour, 2)

            # Score bar (filled rectangle on top of bbox)
            bar_w = x2 - x1
            bar_filled = int(bar_w * score / 100)
            cv2.rectangle(frame, (x1, y1 - 8), (x2, y1), (50, 50, 50), -1)
            cv2.rectangle(frame, (x1, y1 - 8), (x1 + bar_filled, y1), colour, -1)

            # Label background
            label = f"#{student.track_id} | {int(score)}% | {student.behaviour.value}"
            (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
            cv2.rectangle(frame, (x1, y1 - 8 - lh - 6), (x1 + lw + 4, y1 - 8), colour, -1)
            cv2.putText(
                frame, label,
                (x1 + 2, y1 - 8 - 3),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA
            )

            # Emotion tag
            if student.dominant_emotion:
                cv2.putText(
                    frame, student.dominant_emotion,
                    (x1 + 2, y2 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, colour, 1, cv2.LINE_AA
                )

        # HUD overlay
        hud = f"Students: {len(self.students)}  |  Class Attention: {self.attention.get_class_average(set(self.students.keys()))}%  |  FPS: {self.fps_actual:.1f}"
        cv2.rectangle(frame, (0, 0), (frame.shape[1], 30), (20, 20, 20), -1)
        cv2.putText(frame, hud, (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 230, 255), 1, cv2.LINE_AA)
        return frame

    def _student_to_dict(self, s: StudentState) -> dict:
        return {
            "track_id": int(s.track_id),
            "bbox": [int(x) for x in s.bbox],
            "attention_score": float(s.attention_score),
            "attention_label": self.attention.score_label(s.attention_score),
            "attention_color": self.attention.score_color(s.attention_score),
            "yaw": float(s.yaw) if s.yaw is not None else None,
            "pitch": float(s.pitch) if s.pitch is not None else None,
            "is_attentive": bool(s.is_attentive_hp) if s.is_attentive_hp is not None else None,
            "behaviour": s.behaviour.value,
            "behaviour_confidence": float(round(s.behaviour_confidence, 2)),
            "dominant_emotion": s.dominant_emotion,
            "emotion_valence": float(round(s.emotion_valence, 3)),
        }

    def _update_fps(self):
        now = time.time()
        elapsed = now - self._t_last
        if elapsed > 0:
            self.fps_actual = 0.9 * self.fps_actual + 0.1 * (1.0 / elapsed)
        self._t_last = now

    def get_session_summary(self) -> dict:
        """Returns a summary dict at end of session."""
        return {
            "total_frames": self.frame_count,
            "avg_fps": round(self.fps_actual, 1),
            "peak_students": len(self.students),
        }

    def release(self):
        """Clean up all models."""
        self.head_pose.release()
        self.behaviour.release()
        self.is_running = False
        logger.info("Pipeline released.")
