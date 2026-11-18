"""
ClassVisionAI — Break Advisor Module
Attention-adaptive break recommendation system.
Recommends breaks based on actual attention data, not fixed intervals.
"""

import time
from typing import Optional, Dict
from dataclasses import dataclass
from collections import deque


@dataclass
class BreakRecommendation:
    should_break: bool
    reason: str
    suggested_duration_minutes: int
    urgency: str  # 'low', 'medium', 'high'
    time_since_last_break: int  # minutes


class BreakAdvisor:
    """
    Attention-adaptive break recommendation system.
    Recommends breaks based on actual attention data, not fixed intervals.
    """
    
    def __init__(self):
        self.attention_history: deque = deque(maxlen=300)  # 5 min at 1 sample/sec
        self.last_break_time: Optional[float] = None
        self.last_recommendation_time: Optional[float] = None
        self.recommendation_cooldown = 300  # 5 minutes between recommendations
        self.session_start_time: Optional[float] = None
        
    def start_session(self):
        """Call when session starts"""
        self.session_start_time = time.time()
        self.last_break_time = time.time()
        self.attention_history.clear()
        
    def recommend_break(self, session_data: Dict) -> Optional[BreakRecommendation]:
        """
        Analyze attention data and recommend break if needed.
        Call this every 30 seconds from the frame loop.
        """
        if not self.session_start_time:
            self.start_session()
        
        current_attention = session_data.get('class_attention', 0)
        self.attention_history.append({
            'time': time.time(),
            'attention': current_attention
        })
        
        now = time.time()
        time_since_last_break = (now - self.last_break_time) / 60  # minutes
        
        # Don't recommend if we just recommended recently
        if self.last_recommendation_time:
            if (now - self.last_recommendation_time) < self.recommendation_cooldown:
                return None
        
        # Pattern 1: Declining attention for 10+ consecutive minutes
        if self._is_attention_declining():
            self.last_recommendation_time = now
            return BreakRecommendation(
                should_break=True,
                reason="Attention has been declining steadily",
                suggested_duration_minutes=5,
                urgency='medium',
                time_since_last_break=int(time_since_last_break)
            )
        
        # Pattern 2: Low attention for extended period
        if self._is_attention_low() and time_since_last_break >= 20:
            self.last_recommendation_time = now
            return BreakRecommendation(
                should_break=True,
                reason="Class attention below 35% for 5+ minutes",
                suggested_duration_minutes=10,
                urgency='high',
                time_since_last_break=int(time_since_last_break)
            )
        
        # Pattern 3: Hard cap - 45 minutes since last break
        if time_since_last_break >= 45:
            self.last_recommendation_time = now
            return BreakRecommendation(
                should_break=True,
                reason="45 minutes since last break",
                suggested_duration_minutes=10,
                urgency='medium',
                time_since_last_break=int(time_since_last_break)
            )
        
        return None
    
    def acknowledge_break(self, duration_minutes: int):
        """Call when instructor starts a break"""
        self.last_break_time = time.time()
        self.last_recommendation_time = None
        self.attention_history.clear()
    
    def _is_attention_declining(self) -> bool:
        """Check if attention has been declining for 10+ minutes"""
        if len(self.attention_history) < 120:  # Need at least 2 minutes of data
            return False
        
        # Calculate slope over last 10 minutes
        recent = list(self.attention_history)[-600:]  # Last 10 min
        if len(recent) < 60:
            return False
        
        # Simple linear regression slope
        n = len(recent)
        x = list(range(n))
        y = [p['attention'] for p in recent]
        
        x_mean = sum(x) / n
        y_mean = sum(y) / n
        
        numerator = sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
        
        if denominator == 0:
            return False
        
        slope = numerator / denominator
        
        # Negative slope < -2 means declining
        return slope < -2
    
    def _is_attention_low(self) -> bool:
        """Check if attention has been below 35% for 5+ minutes"""
        if len(self.attention_history) < 60:  # Need at least 1 minute
            return False
        
        recent = list(self.attention_history)[-300:]  # Last 5 minutes
        low_count = sum(1 for p in recent if p['attention'] < 35)
        
        # If more than 80% of samples are low
        return (low_count / len(recent)) > 0.8
