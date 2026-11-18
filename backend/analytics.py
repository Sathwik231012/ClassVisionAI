"""
ClassVisionAI — Analytics Module
Provides analytics data aggregation for sessions
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from backend.database import StudentSnapshot, ClassSession
from collections import defaultdict


async def get_session_analytics(session_id: int, db: AsyncSession) -> Dict:
    """
    Get comprehensive analytics for a completed session
    """
    # Get all snapshots for this session
    result = await db.execute(
        select(StudentSnapshot)
        .where(StudentSnapshot.session_id == session_id)
        .order_by(StudentSnapshot.timestamp)
    )
    snapshots = result.scalars().all()
    
    if not snapshots:
        return _empty_analytics()
    
    # Attention distribution (5 buckets)
    attention_dist = {"0-20": 0, "21-40": 0, "41-60": 0, "61-80": 0, "81-100": 0}
    attention_scores = []
    
    for snap in snapshots:
        score = snap.attention_score or 0
        attention_scores.append(score)
        
        if score <= 20:
            attention_dist["0-20"] += 1
        elif score <= 40:
            attention_dist["21-40"] += 1
        elif score <= 60:
            attention_dist["41-60"] += 1
        elif score <= 80:
            attention_dist["61-80"] += 1
        else:
            attention_dist["81-100"] += 1
    
    # Attention timeline (grouped by minute)
    timeline = defaultdict(list)
    for snap in snapshots:
        minute_key = snap.timestamp.replace(second=0, microsecond=0)
        if snap.attention_score:
            timeline[minute_key].append(snap.attention_score)
    
    attention_timeline = [
        {"timestamp": ts.isoformat(), "avg_score": sum(scores) / len(scores)}
        for ts, scores in sorted(timeline.items())
    ]
    
    # Behaviour timeline
    behaviour_timeline_dict = defaultdict(lambda: {
        "attentive": 0, "head_down": 0, "phone_usage": 0, 
        "raised_hand": 0, "side_talk": 0
    })
    
    for snap in snapshots:
        minute_key = snap.timestamp.replace(second=0, microsecond=0)
        behaviour = snap.behaviour_state or "unknown"
        if behaviour in behaviour_timeline_dict[minute_key]:
            behaviour_timeline_dict[minute_key][behaviour] += 1
    
    behaviour_timeline = [
        {"timestamp": ts.isoformat(), **counts}
        for ts, counts in sorted(behaviour_timeline_dict.items())
    ]
    
    # Emotion summary
    emotion_summary = defaultdict(int)
    for snap in snapshots:
        if snap.dominant_emotion:
            emotion_summary[snap.dominant_emotion] += 1
    
    # Calculate stats
    peak_attention = max(attention_scores) if attention_scores else 0
    lowest_attention = min(attention_scores) if attention_scores else 0
    avg_attention = sum(attention_scores) / len(attention_scores) if attention_scores else 0
    
    return {
        "attention_distribution": attention_dist,
        "attention_timeline": attention_timeline,
        "behaviour_timeline": behaviour_timeline,
        "emotion_summary": dict(emotion_summary),
        "peak_attention": round(peak_attention, 1),
        "lowest_attention": round(lowest_attention, 1),
        "avg_attention": round(avg_attention, 1),
    }


def get_current_analytics(latest_data: Dict, attention_history: List) -> Dict:
    """
    Get analytics for currently active session from in-memory data
    """
    students = latest_data.get("students", [])
    
    if not students:
        return _empty_analytics()
    
    # Attention distribution from current students
    attention_dist = {"0-20": 0, "21-40": 0, "41-60": 0, "61-80": 0, "81-100": 0}
    
    for student in students:
        score = student.get("attention_score", 0)
        if score <= 20:
            attention_dist["0-20"] += 1
        elif score <= 40:
            attention_dist["21-40"] += 1
        elif score <= 60:
            attention_dist["41-60"] += 1
        elif score <= 80:
            attention_dist["61-80"] += 1
        else:
            attention_dist["81-100"] += 1
    
    # Attention timeline from history
    attention_timeline = [
        {"timestamp": datetime.fromtimestamp(point["t"] / 1000).isoformat(), 
         "avg_score": point["v"]}
        for point in attention_history
    ]
    
    # Behaviour counts
    behaviour_counts = {
        "attentive": 0, "head_down": 0, "phone_usage": 0,
        "raised_hand": 0, "side_talk": 0
    }
    
    for student in students:
        behaviour = student.get("behaviour", "unknown")
        if behaviour in behaviour_counts:
            behaviour_counts[behaviour] += 1
    
    behaviour_timeline = [{
        "timestamp": datetime.now().isoformat(),
        **behaviour_counts
    }]
    
    # Emotion summary
    emotion_summary = defaultdict(int)
    for student in students:
        emotion = student.get("dominant_emotion")
        if emotion:
            emotion_summary[emotion] += 1
    
    # Stats
    scores = [s.get("attention_score", 0) for s in students]
    peak_attention = max(scores) if scores else 0
    lowest_attention = min(scores) if scores else 0
    avg_attention = sum(scores) / len(scores) if scores else 0
    
    return {
        "attention_distribution": attention_dist,
        "attention_timeline": attention_timeline,
        "behaviour_timeline": behaviour_timeline,
        "emotion_summary": dict(emotion_summary),
        "peak_attention": round(peak_attention, 1),
        "lowest_attention": round(lowest_attention, 1),
        "avg_attention": round(avg_attention, 1),
    }


def _empty_analytics() -> Dict:
    """Return empty analytics structure"""
    return {
        "attention_distribution": {"0-20": 0, "21-40": 0, "41-60": 0, "61-80": 0, "81-100": 0},
        "attention_timeline": [],
        "behaviour_timeline": [],
        "emotion_summary": {},
        "peak_attention": 0,
        "lowest_attention": 0,
        "avg_attention": 0,
    }
