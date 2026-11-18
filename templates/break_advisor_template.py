"""
Template for Break Timer / Attention-Adaptive Pomodoro (CHANGE 6)
Copy this code and adapt as needed
"""

# ═══════════════════════════════════════════════════════════════════════════
# 1. BREAK ADVISOR MODULE (create backend/break_advisor.py)
# ═══════════════════════════════════════════════════════════════════════════

import time
from typing import Optional, Dict, List
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


# ═══════════════════════════════════════════════════════════════════════════
# 2. BACKEND INTEGRATION (add to backend/app.py)
# ═══════════════════════════════════════════════════════════════════════════

"""
from backend.break_advisor import BreakAdvisor

# Add to global state
_break_advisor: Optional[BreakAdvisor] = None

# In start_session endpoint:
_break_advisor = BreakAdvisor()
_break_advisor.start_session()

# In _frame_loop(), add every 30 seconds:
if _break_advisor and _pipeline:
    recommendation = _break_advisor.recommend_break(_latest_data)
    if recommendation:
        _latest_data['break_recommendation'] = {
            'should_break': recommendation.should_break,
            'reason': recommendation.reason,
            'suggested_duration': recommendation.suggested_duration_minutes,
            'urgency': recommendation.urgency,
            'time_since_last_break': recommendation.time_since_last_break
        }

# Add endpoint:
@app.post("/api/break/acknowledge")
async def acknowledge_break(duration_minutes: int = 5):
    if _break_advisor:
        _break_advisor.acknowledge_break(duration_minutes)
        return {"message": "Break acknowledged"}
    raise HTTPException(400, "No active session")
"""


# ═══════════════════════════════════════════════════════════════════════════
# 3. FRONTEND HTML (add to frontend/index.html)
# ═══════════════════════════════════════════════════════════════════════════

"""
<!-- Add Break Timer Widget (in dashboard page, after KPI cards) -->
<div class="break-timer-widget" id="breakTimer">
  <div class="break-timer-content">
    <div class="break-status" id="breakStatus">Monitoring</div>
    <div class="break-time" id="breakTime">Break in ~30 min</div>
    <svg class="break-progress" viewBox="0 0 100 100">
      <circle cx="50" cy="50" r="45" class="break-progress-bg"/>
      <circle cx="50" cy="50" r="45" class="break-progress-fill" id="breakProgressCircle"/>
    </svg>
    <div class="break-actions hidden" id="breakActions">
      <button class="btn btn-sm" onclick="startBreak(5)">5 min</button>
      <button class="btn btn-sm" onclick="startBreak(10)">10 min</button>
    </div>
    <div class="break-countdown hidden" id="breakCountdown">
      <div class="countdown-time" id="countdownTime">05:00</div>
      <button class="btn btn-sm btn-ghost" onclick="endBreak()">End Early</button>
    </div>
  </div>
</div>

<!-- Break Overlay (shows during break) -->
<div class="break-overlay hidden" id="breakOverlay">
  <div class="break-message">
    <h2>🎓 Break Time</h2>
    <p>Students are on break</p>
  </div>
</div>
"""


# ═══════════════════════════════════════════════════════════════════════════
# 4. FRONTEND JAVASCRIPT (add to frontend/app.js)
# ═══════════════════════════════════════════════════════════════════════════

"""
// Break Timer State
const BreakState = {
  isOnBreak: false,
  breakEndTime: null,
  breakInterval: null,
  lastBreakTime: null,
};

// Handle break recommendation from WebSocket
function handleBreakRecommendation(recommendation) {
  if (!recommendation || !recommendation.should_break) return;
  
  const widget = document.getElementById('breakTimer');
  const status = document.getElementById('breakStatus');
  const time = document.getElementById('breakTime');
  const actions = document.getElementById('breakActions');
  
  // Show recommendation
  widget.classList.add('recommended');
  status.textContent = 'Break Recommended';
  time.textContent = recommendation.reason;
  actions.classList.remove('hidden');
  
  // Pulse animation
  widget.style.animation = 'pulse 2s infinite';
}

async function startBreak(duration) {
  try {
    // Acknowledge break to backend
    await fetch('/api/break/acknowledge', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({duration_minutes: duration})
    });
    
    BreakState.isOnBreak = true;
    BreakState.breakEndTime = Date.now() + (duration * 60 * 1000);
    BreakState.lastBreakTime = Date.now();
    
    // Update UI
    const widget = document.getElementById('breakTimer');
    const actions = document.getElementById('breakActions');
    const countdown = document.getElementById('breakCountdown');
    const overlay = document.getElementById('breakOverlay');
    
    widget.classList.remove('recommended');
    widget.classList.add('active');
    actions.classList.add('hidden');
    countdown.classList.remove('hidden');
    overlay.classList.remove('hidden');
    
    // Start countdown
    BreakState.breakInterval = setInterval(updateBreakCountdown, 1000);
    updateBreakCountdown();
    
    showToast(`Break started: ${duration} minutes`, 'success');
  } catch (e) {
    showToast('Failed to start break', 'error');
  }
}

function updateBreakCountdown() {
  const remaining = BreakState.breakEndTime - Date.now();
  
  if (remaining <= 0) {
    endBreak();
    return;
  }
  
  const minutes = Math.floor(remaining / 60000);
  const seconds = Math.floor((remaining % 60000) / 1000);
  
  const display = document.getElementById('countdownTime');
  display.textContent = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
  
  // Update progress circle
  const totalDuration = BreakState.breakEndTime - BreakState.lastBreakTime;
  const progress = 1 - (remaining / totalDuration);
  const circle = document.getElementById('breakProgressCircle');
  const circumference = 2 * Math.PI * 45;
  circle.style.strokeDashoffset = circumference * (1 - progress);
}

function endBreak() {
  clearInterval(BreakState.breakInterval);
  BreakState.isOnBreak = false;
  
  const widget = document.getElementById('breakTimer');
  const countdown = document.getElementById('breakCountdown');
  const overlay = document.getElementById('breakOverlay');
  const status = document.getElementById('breakStatus');
  const time = document.getElementById('breakTime');
  
  widget.classList.remove('active');
  countdown.classList.add('hidden');
  overlay.classList.add('hidden');
  
  // Show "Break Complete" briefly
  status.textContent = 'Break Complete';
  time.textContent = 'Session resuming...';
  
  setTimeout(() => {
    status.textContent = 'Monitoring';
    time.textContent = 'Break in ~30 min';
  }, 5000);
  
  showToast('Break ended, session resumed', 'success');
}

// Update WebSocket handler to process break recommendations
// In onmessage handler, add:
if (data.break_recommendation) {
  handleBreakRecommendation(data.break_recommendation);
}
"""


# ═══════════════════════════════════════════════════════════════════════════
# 5. FRONTEND CSS (add to frontend/style.css)
# ═══════════════════════════════════════════════════════════════════════════

"""
/* Break Timer Widget */
.break-timer-widget {
  position: fixed;
  top: 80px;
  right: 24px;
  width: 180px;
  background: white;
  border-radius: 12px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.1);
  padding: 16px;
  z-index: 100;
  transition: all 0.3s ease;
}

.break-timer-widget.recommended {
  border: 2px solid #F59E0B;
  box-shadow: 0 4px 20px rgba(245, 158, 11, 0.3);
}

.break-timer-widget.active {
  width: 220px;
  border: 2px solid #3B82F6;
}

.break-timer-content {
  text-align: center;
}

.break-status {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.break-time {
  font-size: 0.85rem;
  margin-top: 4px;
  color: var(--navy);
}

.break-progress {
  width: 80px;
  height: 80px;
  margin: 12px auto;
  transform: rotate(-90deg);
}

.break-progress-bg {
  fill: none;
  stroke: var(--bg);
  stroke-width: 8;
}

.break-progress-fill {
  fill: none;
  stroke: #3B82F6;
  stroke-width: 8;
  stroke-linecap: round;
  stroke-dasharray: 283;
  stroke-dashoffset: 283;
  transition: stroke-dashoffset 1s linear;
}

.break-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}

.break-countdown {
  margin-top: 12px;
}

.countdown-time {
  font-family: 'DM Mono', monospace;
  font-size: 2rem;
  font-weight: 700;
  color: var(--navy);
  margin-bottom: 12px;
}

/* Break Overlay */
.break-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(15, 23, 42, 0.7);
  backdrop-filter: blur(4px);
  z-index: 90;
  display: flex;
  align-items: center;
  justify-content: center;
}

.break-message {
  text-align: center;
  color: white;
}

.break-message h2 {
  font-size: 2.5rem;
  margin-bottom: 12px;
}

.break-message p {
  font-size: 1.2rem;
  opacity: 0.9;
}

@keyframes pulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.05); }
}
"""
