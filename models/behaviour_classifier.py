"""
ClassVisionAI — Behaviour Classifier
Uses MediaPipe Pose (33 keypoints) with rule-based heuristics to classify
5 classroom behaviours: attentive | head_down | phone_usage | raised_hand | side_talk

Rule-based is used for Phase 1 (high reliability, no training data needed).
BiLSTM temporal classifier can be plugged in as a drop-in replacement later.
"""

import numpy as np
import mediapipe as mp
from dataclasses import dataclass
from typing import Optional
from enum import Enum


class BehaviourState(str, Enum):
    ATTENTIVE   = "attentive"
    HEAD_DOWN   = "head_down"
    PHONE_USAGE = "phone_usage"
    RAISED_HAND = "raised_hand"
    SIDE_TALK   = "side_talk"
    UNKNOWN     = "unknown"


# Behaviour engagement weights for attention score
BEHAVIOUR_WEIGHTS = {
    BehaviourState.ATTENTIVE:   1.0,
    BehaviourState.RAISED_HAND: 1.0,
    BehaviourState.SIDE_TALK:   0.3,
    BehaviourState.PHONE_USAGE: 0.1,
    BehaviourState.HEAD_DOWN:   0.0,
    BehaviourState.UNKNOWN:     0.5,
}


@dataclass
class BehaviourResult:
    state: BehaviourState
    confidence: float         # 0–1
    engagement_weight: float  # for attention score


# MediaPipe Pose landmark indices
class PoseLandmark:
    NOSE            = 0
    LEFT_SHOULDER   = 11
    RIGHT_SHOULDER  = 12
    LEFT_ELBOW      = 13
    RIGHT_ELBOW     = 14
    LEFT_WRIST      = 15
    RIGHT_WRIST     = 16
    LEFT_HIP        = 23
    RIGHT_HIP       = 24
    LEFT_EAR        = 7
    RIGHT_EAR       = 8


class BehaviourClassifier:
    """
    Rule-based classroom behaviour classifier.
    Operates on single frames — no temporal modeling required for Phase 1.
    """

    def __init__(self):
        self._mp_pose = mp.solutions.pose
        self.pose = self._mp_pose.Pose(
            static_image_mode=False,
            model_complexity=1,          # 0=lite, 1=full, 2=heavy — balanced
            smooth_landmarks=True,
            enable_segmentation=False,
            min_detection_confidence=0.55,
            min_tracking_confidence=0.5,
        )

    def classify(
        self,
        person_crop_rgb: np.ndarray,
        yaw: Optional[float] = None,
        pitch: Optional[float] = None,
    ) -> BehaviourResult:
        """
        Classify behaviour from a cropped person ROI (RGB).
        yaw/pitch are head pose angles from HeadPoseEstimator (optional but improve accuracy).
        """
        if person_crop_rgb is None or person_crop_rgb.size == 0:
            return BehaviourResult(
                state=BehaviourState.UNKNOWN,
                confidence=0.0,
                engagement_weight=0.5,
            )

        result = self.pose.process(person_crop_rgb)
        lms = result.pose_landmarks

        if lms is None:
            return self._head_pose_fallback(yaw, pitch)

        # Normalized landmarks [0,1] relative to crop
        pts = {i: (lm.x, lm.y, lm.visibility) for i, lm in enumerate(lms.landmark)}

        # ── 1. Raised hand ─────────────────────────────────────────────────
        raised = self._check_raised_hand(pts)
        if raised:
            return BehaviourResult(
                state=BehaviourState.RAISED_HAND,
                confidence=0.90,
                engagement_weight=BEHAVIOUR_WEIGHTS[BehaviourState.RAISED_HAND],
            )

        # ── 2. Phone usage ─────────────────────────────────────────────────
        phone = self._check_phone_usage(pts, yaw, pitch)
        if phone:
            return BehaviourResult(
                state=BehaviourState.PHONE_USAGE,
                confidence=0.80,
                engagement_weight=BEHAVIOUR_WEIGHTS[BehaviourState.PHONE_USAGE],
            )

        # ── 3. Head down / sleeping ────────────────────────────────────────
        head_down = self._check_head_down(pts, pitch)
        if head_down:
            return BehaviourResult(
                state=BehaviourState.HEAD_DOWN,
                confidence=0.85,
                engagement_weight=BEHAVIOUR_WEIGHTS[BehaviourState.HEAD_DOWN],
            )

        # ── 4. Side talk ───────────────────────────────────────────────────
        side = self._check_side_talk(pts, yaw)
        if side:
            return BehaviourResult(
                state=BehaviourState.SIDE_TALK,
                confidence=0.70,
                engagement_weight=BEHAVIOUR_WEIGHTS[BehaviourState.SIDE_TALK],
            )

        # ── 5. Default: attentive ──────────────────────────────────────────
        return BehaviourResult(
            state=BehaviourState.ATTENTIVE,
            confidence=0.75,
            engagement_weight=BEHAVIOUR_WEIGHTS[BehaviourState.ATTENTIVE],
        )

    # ─── Rule Helpers ─────────────────────────────────────────────────────────

    def _check_raised_hand(self, pts: dict) -> bool:
        """Wrist above ipsilateral shoulder — clearly raised hand."""
        lw = pts.get(PoseLandmark.LEFT_WRIST)
        rw = pts.get(PoseLandmark.RIGHT_WRIST)
        ls = pts.get(PoseLandmark.LEFT_SHOULDER)
        rs = pts.get(PoseLandmark.RIGHT_SHOULDER)

        if lw and ls and lw[2] > 0.5 and ls[2] > 0.5:
            if lw[1] < ls[1] - 0.1:  # y is inverted (0=top)
                return True
        if rw and rs and rw[2] > 0.5 and rs[2] > 0.5:
            if rw[1] < rs[1] - 0.1:
                return True
        return False

    def _check_phone_usage(self, pts: dict, yaw: Optional[float], pitch: Optional[float]) -> bool:
        """
        Heuristic: wrists close to face/chest + head tilted down + arms bent.
        Combined with head pose for stronger signal.
        """
        nose = pts.get(PoseLandmark.NOSE)
        lw = pts.get(PoseLandmark.LEFT_WRIST)
        rw = pts.get(PoseLandmark.RIGHT_WRIST)
        le = pts.get(PoseLandmark.LEFT_ELBOW)
        re = pts.get(PoseLandmark.RIGHT_ELBOW)
        ls = pts.get(PoseLandmark.LEFT_SHOULDER)
        rs = pts.get(PoseLandmark.RIGHT_SHOULDER)

        # Check 1: Wrist near face/upper chest area
        wrist_near_face = False
        wrist_in_phone_zone = False
        
        if nose and (ls and rs):
            nx, ny = nose[0], nose[1]
            shoulder_y = (ls[1] + rs[1]) / 2 if (ls and rs) else ny + 0.2
            
            for wrist in [lw, rw]:
                if wrist and wrist[2] > 0.3:  # Lower visibility threshold
                    wx, wy = wrist[0], wrist[1]
                    dist = np.hypot(wx - nx, wy - ny)
                    
                    # Wrist close to face
                    if dist < 0.30:  # Increased distance threshold
                        wrist_near_face = True
                    
                    # Wrist in "phone zone" (between face and chest)
                    if wy > ny and wy < shoulder_y + 0.15:
                        wrist_in_phone_zone = True

        # Check 2: Head pitched down (looking at phone)
        head_pitched_down = pitch is not None and pitch > 10  # More sensitive threshold

        # Check 3: Both hands in front of body (typical phone holding posture)
        both_hands_forward = False
        if lw and rw and lw[2] > 0.3 and rw[2] > 0.3:
            # Both wrists visible and close together (holding phone)
            wrist_dist = np.hypot(lw[0] - rw[0], lw[1] - rw[1])
            if wrist_dist < 0.20:  # Hands close together
                both_hands_forward = True

        # Check 4: Elbow bent (arm not hanging down)
        arm_bent = False
        arms_raised = False
        for (elbow, wrist, shoulder) in [(le, lw, ls), (re, rw, rs)]:
            if elbow and wrist and elbow[2] > 0.3 and wrist[2] > 0.3:
                # Wrist higher than elbow (arm bent upward)
                if wrist[1] < elbow[1]:
                    arm_bent = True
                # Elbow raised (not hanging)
                if shoulder and shoulder[2] > 0.3:
                    if elbow[1] < shoulder[1] + 0.15:
                        arms_raised = True

        # Multiple detection patterns for phone usage
        patterns = [
            # Pattern 1: Classic phone holding - wrist near face + looking down
            (wrist_near_face and head_pitched_down),
            # Pattern 2: Phone in lap/chest - wrist in zone + looking down + arms bent
            (wrist_in_phone_zone and head_pitched_down and arm_bent),
            # Pattern 3: Two-handed phone use - both hands together + looking down
            (both_hands_forward and head_pitched_down),
            # Pattern 4: One-handed phone - wrist near face + arm raised
            (wrist_near_face and arms_raised),
            # Pattern 5: Texting posture - wrist in zone + both hands forward
            (wrist_in_phone_zone and both_hands_forward),
        ]

        return any(patterns)

    def _check_head_down(self, pts: dict, pitch: Optional[float]) -> bool:
        """
        Head very low: nose near or below shoulder line.
        Or pitch > 35 degrees if head pose available.
        """
        if pitch is not None and pitch > 35:
            return True

        nose = pts.get(PoseLandmark.NOSE)
        ls   = pts.get(PoseLandmark.LEFT_SHOULDER)
        rs   = pts.get(PoseLandmark.RIGHT_SHOULDER)

        if nose and ls and rs and ls[2] > 0.4 and rs[2] > 0.4:
            shoulder_y = (ls[1] + rs[1]) / 2
            if nose[1] > shoulder_y - 0.05:  # nose at or below shoulders
                return True
        return False

    def _check_side_talk(self, pts: dict, yaw: Optional[float]) -> bool:
        """
        Large sustained yaw indicates looking sideways (talking to neighbor).
        """
        if yaw is not None and abs(yaw) > 40:
            return True

        # Fallback: ear landmark significantly closer to camera
        le = pts.get(PoseLandmark.LEFT_EAR)
        re = pts.get(PoseLandmark.RIGHT_EAR)
        if le and re and le[2] > 0.3 and re[2] > 0.3:
            # If one ear is much more visible — head turned
            vis_diff = abs(le[2] - re[2])
            if vis_diff > 0.5:
                return True
        return False

    def _head_pose_fallback(self, yaw: Optional[float], pitch: Optional[float]) -> BehaviourResult:
        """When pose landmarks not detected, fall back to head pose only."""
        if pitch is not None and pitch > 35:
            return BehaviourResult(BehaviourState.HEAD_DOWN, 0.60, BEHAVIOUR_WEIGHTS[BehaviourState.HEAD_DOWN])
        if yaw is not None and abs(yaw) > 40:
            return BehaviourResult(BehaviourState.SIDE_TALK, 0.55, BEHAVIOUR_WEIGHTS[BehaviourState.SIDE_TALK])
        return BehaviourResult(BehaviourState.UNKNOWN, 0.40, BEHAVIOUR_WEIGHTS[BehaviourState.UNKNOWN])

    def get_engagement_weight(self, state: BehaviourState) -> float:
        return BEHAVIOUR_WEIGHTS.get(state, 0.5)

    def release(self):
        self.pose.close()
