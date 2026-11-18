"""
ClassVisionAI — Head Pose Estimator
Uses MediaPipe Face Mesh (468 landmarks) + PnP solver to compute
pitch, yaw, and roll. Returns attention classification.
"""

import cv2
import numpy as np
from dataclasses import dataclass
from typing import Optional, Tuple
import mediapipe as mp
from configs.config import config


# ─── 3D reference face model (canonical landmarks in mm) ─────────────────────
# Key points: nose tip, chin, left/right eye corners, left/right mouth corners
MODEL_POINTS_3D = np.array([
    [0.0,       0.0,      0.0],    # Nose tip             (idx 1)
    [0.0,      -63.6,    -12.5],   # Chin                 (idx 152)
    [-43.3,     32.7,    -26.0],   # Left eye, left corner (idx 263)
    [43.3,      32.7,    -26.0],   # Right eye, right corner (idx 33)
    [-28.9,    -28.9,    -24.1],   # Left mouth corner    (idx 287)
    [28.9,     -28.9,    -24.1],   # Right mouth corner   (idx 57)
], dtype=np.float64)

# Corresponding MediaPipe face mesh landmark indices
LANDMARK_INDICES = [1, 152, 263, 33, 287, 57]


@dataclass
class HeadPoseResult:
    yaw: float           # degrees (+right, -left)
    pitch: float         # degrees (+down, -up)
    roll: float          # degrees
    is_attentive: bool
    rotation_vec: Optional[np.ndarray] = None
    translation_vec: Optional[np.ndarray] = None


class HeadPoseEstimator:
    """
    Wraps MediaPipe Face Mesh for efficient head pose estimation.
    One instance per pipeline — not per student (for performance).
    """

    def __init__(self, frame_width: int = 1280, frame_height: int = 720):
        self.frame_width = frame_width
        self.frame_height = frame_height

        # Camera intrinsic matrix (approximated from frame size)
        focal_length = frame_width
        cx, cy = frame_width / 2, frame_height / 2
        self.camera_matrix = np.array([
            [focal_length, 0,            cx],
            [0,            focal_length, cy],
            [0,            0,            1 ],
        ], dtype=np.float64)
        self.dist_coeffs = np.zeros((4, 1), dtype=np.float64)  # assume no lens distortion

        # MediaPipe Face Mesh
        self._mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = self._mp_face_mesh.FaceMesh(
            max_num_faces=30,          # supports large classrooms
            refine_landmarks=True,     # iris landmarks for better gaze
            min_detection_confidence=0.6,
            min_tracking_confidence=0.5,
        )

        self.yaw_thr = config.YAW_THRESHOLD
        self.pitch_thr = config.PITCH_THRESHOLD

    def estimate(self, frame_rgb: np.ndarray) -> dict[int, HeadPoseResult]:
        """
        Process one frame and return head pose for all detected faces.
        Returns dict keyed by face index (0-based in frame).
        frame_rgb: RGB numpy array (H, W, 3)
        """
        results = {}
        mp_result = self.face_mesh.process(frame_rgb)

        if not mp_result.multi_face_landmarks:
            return results

        h, w = frame_rgb.shape[:2]

        for face_idx, face_landmarks in enumerate(mp_result.multi_face_landmarks):
            # Extract 2D image points for the 6 reference landmarks
            image_points_2d = []
            for lm_idx in LANDMARK_INDICES:
                lm = face_landmarks.landmark[lm_idx]
                image_points_2d.append([lm.x * w, lm.y * h])
            image_points_2d = np.array(image_points_2d, dtype=np.float64)

            # PnP solver for rotation and translation vectors
            success, rot_vec, trans_vec = cv2.solvePnP(
                MODEL_POINTS_3D,
                image_points_2d,
                self.camera_matrix,
                self.dist_coeffs,
                flags=cv2.SOLVEPNP_ITERATIVE,
            )
            if not success:
                continue

            # Convert rotation vector to Euler angles
            rot_mat, _ = cv2.Rodrigues(rot_vec)
            pitch, yaw, roll = self._rotation_matrix_to_euler(rot_mat)

            is_attentive = (
                abs(yaw) <= self.yaw_thr and abs(pitch) <= self.pitch_thr
            )

            results[face_idx] = HeadPoseResult(
                yaw=round(yaw, 2),
                pitch=round(pitch, 2),
                roll=round(roll, 2),
                is_attentive=is_attentive,
                rotation_vec=rot_vec,
                translation_vec=trans_vec,
            )

        return results

    @staticmethod
    def _rotation_matrix_to_euler(R: np.ndarray) -> Tuple[float, float, float]:
        """Convert 3×3 rotation matrix to pitch, yaw, roll in degrees."""
        sy = np.sqrt(R[0, 0] ** 2 + R[1, 0] ** 2)
        singular = sy < 1e-6

        if not singular:
            pitch = np.degrees(np.arctan2(R[2, 1], R[2, 2]))
            yaw   = np.degrees(np.arctan2(-R[2, 0], sy))
            roll  = np.degrees(np.arctan2(R[1, 0], R[0, 0]))
        else:
            pitch = np.degrees(np.arctan2(-R[1, 2], R[1, 1]))
            yaw   = np.degrees(np.arctan2(-R[2, 0], sy))
            roll  = 0.0

        return pitch, yaw, roll

    def draw_pose_axes(
        self,
        frame: np.ndarray,
        result: HeadPoseResult,
        origin_2d: Tuple[int, int],
        axis_length: float = 50.0,
    ) -> np.ndarray:
        """
        Draw 3D pose axes on frame for visualization.
        origin_2d: (x, y) pixel position to draw from (e.g., nose tip).
        """
        axis_3d = np.float32([
            [axis_length, 0, 0],
            [0, axis_length, 0],
            [0, 0, axis_length],
        ])
        if result.rotation_vec is None:
            return frame

        pts, _ = cv2.projectPoints(
            axis_3d, result.rotation_vec, result.translation_vec,
            self.camera_matrix, self.dist_coeffs
        )
        origin = tuple(map(int, origin_2d))
        cv2.line(frame, origin, tuple(pts[0].ravel().astype(int)), (0, 0, 255), 2)   # X - red
        cv2.line(frame, origin, tuple(pts[1].ravel().astype(int)), (0, 255, 0), 2)   # Y - green
        cv2.line(frame, origin, tuple(pts[2].ravel().astype(int)), (255, 0, 0), 2)   # Z - blue
        return frame

    def release(self):
        self.face_mesh.close()
