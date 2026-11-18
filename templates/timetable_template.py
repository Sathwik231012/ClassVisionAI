"""
Template for Timetable Integration (CHANGE 5)
Copy this code and adapt as needed
"""

# ═══════════════════════════════════════════════════════════════════════════
# 1. DATABASE MODEL (add to backend/database.py)
# ═══════════════════════════════════════════════════════════════════════════

from sqlalchemy import Column, Integer, String, Boolean

class TimetableEntry(Base):
    """Weekly timetable entry for classroom scheduling"""
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


# ═══════════════════════════════════════════════════════════════════════════
# 2. API ENDPOINTS (add to backend/app.py)
# ═══════════════════════════════════════════════════════════════════════════

from datetime import datetime, time as dt_time
from backend.database import TimetableEntry

@app.post("/api/timetable")
async def create_timetable_entry(
    day_of_week: int,
    start_time: str,
    end_time: str,
    subject: str = "",
    instructor: str = "",
    classroom: str = "",
    color_hex: str = "#3B82F6",
    db: AsyncSession = Depends(get_db)
):
    """Create a new timetable entry"""
    entry = TimetableEntry(
        day_of_week=day_of_week,
        start_time=start_time,
        end_time=end_time,
        subject=subject,
        instructor=instructor,
        classroom=classroom,
        color_hex=color_hex,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return {"id": entry.id, "message": "Timetable entry created"}


@app.get("/api/timetable")
async def list_timetable(db: AsyncSession = Depends(get_db)):
    """List all timetable entries"""
    result = await db.execute(
        select(TimetableEntry).where(TimetableEntry.is_active == True).order_by(TimetableEntry.day_of_week, TimetableEntry.start_time)
    )
    entries = result.scalars().all()
    return [
        {
            "id": e.id,
            "day_of_week": e.day_of_week,
            "start_time": e.start_time,
            "end_time": e.end_time,
            "subject": e.subject,
            "instructor": e.instructor,
            "classroom": e.classroom,
            "color_hex": e.color_hex,
        }
        for e in entries
    ]


@app.put("/api/timetable/{entry_id}")
async def update_timetable_entry(
    entry_id: int,
    day_of_week: int = None,
    start_time: str = None,
    end_time: str = None,
    subject: str = None,
    instructor: str = None,
    classroom: str = None,
    color_hex: str = None,
    db: AsyncSession = Depends(get_db)
):
    """Update a timetable entry"""
    result = await db.execute(select(TimetableEntry).where(TimetableEntry.id == entry_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(404, "Entry not found")
    
    if day_of_week is not None: entry.day_of_week = day_of_week
    if start_time: entry.start_time = start_time
    if end_time: entry.end_time = end_time
    if subject: entry.subject = subject
    if instructor: entry.instructor = instructor
    if classroom: entry.classroom = classroom
    if color_hex: entry.color_hex = color_hex
    
    await db.commit()
    return {"message": "Entry updated"}


@app.delete("/api/timetable/{entry_id}")
async def delete_timetable_entry(entry_id: int, db: AsyncSession = Depends(get_db)):
    """Delete (soft delete) a timetable entry"""
    result = await db.execute(select(TimetableEntry).where(TimetableEntry.id == entry_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(404, "Entry not found")
    
    entry.is_active = False
    await db.commit()
    return {"message": "Entry deleted"}


@app.get("/api/timetable/now")
async def get_current_timetable_entry(db: AsyncSession = Depends(get_db)):
    """Get the timetable entry matching current day and time"""
    now = datetime.now()
    current_day = now.weekday()  # 0=Monday
    current_time = now.strftime("%H:%M")
    
    result = await db.execute(
        select(TimetableEntry).where(
            TimetableEntry.day_of_week == current_day,
            TimetableEntry.is_active == True
        )
    )
    entries = result.scalars().all()
    
    # Find entry where current_time is between start_time and end_time
    for entry in entries:
        if entry.start_time <= current_time <= entry.end_time:
            return {
                "id": entry.id,
                "subject": entry.subject,
                "instructor": entry.instructor,
                "classroom": entry.classroom,
                "start_time": entry.start_time,
                "end_time": entry.end_time,
            }
    
    return {"message": "No class scheduled now"}


# ═══════════════════════════════════════════════════════════════════════════
# 3. FRONTEND HTML (add to frontend/index.html)
# ═══════════════════════════════════════════════════════════════════════════

"""
<!-- Add to sidebar navigation -->
<a class="nav-item" data-page="timetable" onclick="showPage('timetable')">
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
    <rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/>
    <line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
  </svg>
  Timetable
</a>

<!-- Add new page section -->
<section class="page" id="page-timetable">
  <div class="card">
    <div class="card-header">
      <span class="card-title">Weekly Timetable</span>
      <button class="btn btn-sm" onclick="showAddTimetableModal()">Add Class</button>
    </div>
    <div class="timetable-grid" id="timetableGrid">
      <!-- Generated by JavaScript -->
    </div>
  </div>
</section>

<!-- Add Timetable Modal -->
<div class="modal-overlay hidden" id="timetableModal">
  <div class="modal">
    <div class="modal-header">
      <h2>Add Class to Timetable</h2>
      <button class="modal-close" onclick="closeTimetableModal()">✕</button>
    </div>
    <div class="modal-body">
      <div class="form-group">
        <label>Day</label>
        <select id="tt-day">
          <option value="0">Monday</option>
          <option value="1">Tuesday</option>
          <option value="2">Wednesday</option>
          <option value="3">Thursday</option>
          <option value="4">Friday</option>
          <option value="5">Saturday</option>
          <option value="6">Sunday</option>
        </select>
      </div>
      <div class="form-group">
        <label>Start Time</label>
        <input type="time" id="tt-start" value="09:00" />
      </div>
      <div class="form-group">
        <label>End Time</label>
        <input type="time" id="tt-end" value="10:00" />
      </div>
      <div class="form-group">
        <label>Subject</label>
        <input type="text" id="tt-subject" placeholder="e.g. Physics" />
      </div>
      <div class="form-group">
        <label>Instructor</label>
        <input type="text" id="tt-instructor" placeholder="Instructor name" />
      </div>
      <div class="form-group">
        <label>Classroom</label>
        <input type="text" id="tt-classroom" placeholder="e.g. Room 101" />
      </div>
      <div class="form-group">
        <label>Color</label>
        <input type="color" id="tt-color" value="#3B82F6" />
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-ghost" onclick="closeTimetableModal()">Cancel</button>
      <button class="btn btn-start" onclick="saveTimetableEntry()">Save</button>
    </div>
  </div>
</div>
"""


# ═══════════════════════════════════════════════════════════════════════════
# 4. FRONTEND JAVASCRIPT (add to frontend/app.js)
# ═══════════════════════════════════════════════════════════════════════════

"""
// Add to PAGE_META
timetable: { title: 'Timetable', sub: 'Weekly class schedule' },

// Timetable functions
async function loadTimetable() {
  try {
    const r = await fetch('/api/timetable');
    const entries = await r.json();
    renderTimetableGrid(entries);
  } catch (e) {
    console.error('Failed to load timetable:', e);
  }
}

function renderTimetableGrid(entries) {
  const grid = document.getElementById('timetableGrid');
  const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
  const hours = Array.from({length: 13}, (_, i) => i + 7); // 7am to 7pm
  
  let html = '<div class="tt-header">';
  html += '<div class="tt-time-col">Time</div>';
  days.forEach(day => {
    html += `<div class="tt-day-col">${day}</div>`;
  });
  html += '</div>';
  
  hours.forEach(hour => {
    html += '<div class="tt-row">';
    html += `<div class="tt-time-cell">${hour}:00</div>`;
    
    days.forEach((day, dayIdx) => {
      const dayEntries = entries.filter(e => e.day_of_week === dayIdx);
      const hourStr = String(hour).padStart(2, '0');
      const cellEntries = dayEntries.filter(e => 
        e.start_time.startsWith(hourStr)
      );
      
      html += '<div class="tt-cell" onclick="addTimetableEntry(' + dayIdx + ', \'' + hourStr + ':00\')">';
      cellEntries.forEach(entry => {
        html += `<div class="tt-entry" style="background:${entry.color_hex}" onclick="event.stopPropagation(); editTimetableEntry(${entry.id})">
          <strong>${entry.subject}</strong><br>
          <small>${entry.instructor}</small><br>
          <small>${entry.start_time}-${entry.end_time}</small>
        </div>`;
      });
      html += '</div>';
    });
    html += '</div>';
  });
  
  grid.innerHTML = html;
}

function showAddTimetableModal() {
  document.getElementById('timetableModal').classList.remove('hidden');
}

function closeTimetableModal() {
  document.getElementById('timetableModal').classList.add('hidden');
}

async function saveTimetableEntry() {
  const data = {
    day_of_week: parseInt(document.getElementById('tt-day').value),
    start_time: document.getElementById('tt-start').value,
    end_time: document.getElementById('tt-end').value,
    subject: document.getElementById('tt-subject').value,
    instructor: document.getElementById('tt-instructor').value,
    classroom: document.getElementById('tt-classroom').value,
    color_hex: document.getElementById('tt-color').value,
  };
  
  try {
    const r = await fetch('/api/timetable', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(data)
    });
    if (r.ok) {
      showToast('Timetable entry added', 'success');
      closeTimetableModal();
      loadTimetable();
    }
  } catch (e) {
    showToast('Failed to add entry', 'error');
  }
}

// Update showPage to load timetable
// Add: if (id === 'timetable') loadTimetable();

// Add "Load from Timetable" button to session start modal
async function loadFromTimetable() {
  try {
    const r = await fetch('/api/timetable/now');
    const data = await r.json();
    if (data.subject) {
      document.getElementById('inp-session-name').value = `${data.subject} Class`;
      document.getElementById('inp-subject').value = data.subject;
      document.getElementById('inp-instructor').value = data.instructor;
      showToast('Loaded from timetable', 'success');
    } else {
      showToast('No class scheduled now', 'info');
    }
  } catch (e) {
    console.error('Failed to load from timetable:', e);
  }
}
"""


# ═══════════════════════════════════════════════════════════════════════════
# 5. FRONTEND CSS (add to frontend/style.css)
# ═══════════════════════════════════════════════════════════════════════════

"""
/* Timetable Grid */
.timetable-grid {
  display: flex;
  flex-direction: column;
  overflow-x: auto;
}

.tt-header {
  display: grid;
  grid-template-columns: 80px repeat(7, 1fr);
  border-bottom: 2px solid var(--border);
  font-weight: 600;
  background: var(--bg);
}

.tt-day-col, .tt-time-col {
  padding: 12px;
  text-align: center;
  font-size: 0.85rem;
}

.tt-row {
  display: grid;
  grid-template-columns: 80px repeat(7, 1fr);
  border-bottom: 1px solid var(--border);
  min-height: 60px;
}

.tt-time-cell {
  padding: 8px;
  text-align: center;
  font-size: 0.75rem;
  color: var(--text-muted);
  background: var(--bg);
}

.tt-cell {
  padding: 4px;
  border-left: 1px solid var(--border);
  cursor: pointer;
  transition: background 0.2s;
}

.tt-cell:hover {
  background: var(--bg);
}

.tt-entry {
  padding: 6px 8px;
  border-radius: 4px;
  color: white;
  font-size: 0.75rem;
  margin-bottom: 4px;
  cursor: pointer;
  transition: transform 0.2s;
}

.tt-entry:hover {
  transform: scale(1.02);
}

.tt-entry strong {
  display: block;
  font-size: 0.85rem;
}
"""
