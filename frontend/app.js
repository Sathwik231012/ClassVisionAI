/* ══════════════════════════════════════════════════════════════════════════
   ClassVisionAI — Frontend Application
   Handles: WebSocket connection, real-time metrics rendering, charts,
            session management, page navigation.
   ══════════════════════════════════════════════════════════════════════════ */

'use strict';

// ─── State ────────────────────────────────────────────────────────────────────
const State = {
  ws: null,
  isRunning: false,
  sessionId: null,
  sessionStart: null,
  latestData: {},
  attentionHistory: [],  // { t: timestamp, v: value }
  behaviourHistory: [],
  maxHistoryPoints: 60,
  reconnectTimer: null,
  reconnectDelay: 2000,
  durationTimer: null,  // Timer for session duration updates
};

// Break Timer State
const BreakState = {
  isOnBreak: false,
  breakEndTime: null,
  breakInterval: null,
  lastBreakTime: null,
};

// ─── Chart Instances ──────────────────────────────────────────────────────────
let attentionChart   = null;
let distributionChart = null;
let behaviourTimeChart = null;

// ─── Init ─────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // Check authentication
  const user = localStorage.getItem('classvision_user') || sessionStorage.getItem('classvision_user');
  if (!user) {
    window.location.href = '/';
    return;
  }
  
  // Show username in UI
  const usernameDisplay = document.getElementById('username-display');
  if (usernameDisplay) {
    usernameDisplay.textContent = user;
  }
  
  initCharts();
  startClock();
  loadSessions();
  checkInitialStatus();
  showDevice();
});

async function showDevice() {
  const labels = { mps: 'MPS · Apple Silicon', cuda: 'CUDA · NVIDIA GPU', cpu: 'CPU' };
  try {
    const r = await fetch('/api/health');
    const d = await r.json();
    const badge = document.getElementById('deviceBadge');
    if (badge) badge.textContent = labels[d.device] || d.device;
  } catch (e) { /* backend not ready yet */ }
}

async function checkInitialStatus() {
  try {
    const r = await fetch('/api/session/status');
    const d = await r.json();
    if (d.is_running) {
      State.isRunning = true;
      State.sessionId = d.session_id;
      State.sessionStart = Date.now();
      onSessionStarted();
    }
  } catch (e) { /* backend not ready yet */ }
}

// ─── Page Navigation ──────────────────────────────────────────────────────────
const PAGE_META = {
  dashboard: { title: 'Dashboard',    sub: 'Overview · Real-time Classroom Intelligence' },
  students:  { title: 'Students',     sub: 'Per-student attention & behaviour analysis' },
  analytics: { title: 'Analytics',    sub: 'Trends & distributions' },
  sessions:  { title: 'Sessions',     sub: 'Session history & reports' },
  timetable: { title: 'Timetable',    sub: 'Weekly class schedule' },
};

function showPage(id) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  const page = document.getElementById(`page-${id}`);
  if (page) page.classList.add('active');
  const nav = document.querySelector(`[data-page="${id}"]`);
  if (nav) nav.classList.add('active');
  const meta = PAGE_META[id];
  if (meta) {
    document.getElementById('pageTitle').textContent = meta.title;
    document.getElementById('breadcrumb').textContent = meta.sub;
  }
  if (id === 'sessions') loadSessions();
  if (id === 'analytics') loadAnalytics();
  if (id === 'timetable') loadTimetable();
}

// ─── Session Management ───────────────────────────────────────────────────────
function startSession() {
  loadTimetableDropdown();
  document.getElementById('sessionModal').classList.remove('hidden');
}

async function loadTimetableDropdown() {
  try {
    const r = await fetch('/api/timetable');
    const entries = await r.json();
    const selector = document.getElementById('timetable-selector');
    
    // Clear existing options except the first one
    selector.innerHTML = '<option value="">-- Select a class --</option>';
    
    if (entries.length === 0) {
      selector.innerHTML = '<option value="">No classes in timetable</option>';
      return;
    }
    
    // Add all timetable entries
    const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
    entries.forEach(entry => {
      const option = document.createElement('option');
      option.value = entry.id;
      option.textContent = `${days[entry.day_of_week]} ${entry.start_time}-${entry.end_time}: ${entry.subject}`;
      option.dataset.subject = entry.subject;
      option.dataset.instructor = entry.instructor;
      option.dataset.classroom = entry.classroom;
      selector.appendChild(option);
    });
  } catch (e) {
    console.error('Failed to load timetable:', e);
  }
}

function loadSelectedTimetableEntry() {
  const selector = document.getElementById('timetable-selector');
  const selectedOption = selector.options[selector.selectedIndex];
  
  if (!selectedOption.value) return;
  
  const subject = selectedOption.dataset.subject || '';
  const instructor = selectedOption.dataset.instructor || '';
  const classroom = selectedOption.dataset.classroom || '';
  
  document.getElementById('inp-session-name').value = subject ? `${subject} Class` : 'Classroom Session';
  document.getElementById('inp-subject').value = subject;
  document.getElementById('inp-instructor').value = instructor;
  
  showToast('Loaded from timetable', 'success');
}

function closeModal() {
  document.getElementById('sessionModal').classList.add('hidden');
}

async function confirmStart() {
  const name = document.getElementById('inp-session-name').value || 'Classroom Session';
  const subject = document.getElementById('inp-subject').value;
  const instructor = document.getElementById('inp-instructor').value;

  closeModal();
  showToast('Starting session…', 'info');

  try {
    const r = await fetch(
      `/api/session/start?session_name=${encodeURIComponent(name)}&subject=${encodeURIComponent(subject)}&instructor=${encodeURIComponent(instructor)}`,
      { method: 'POST' }
    );
    if (!r.ok) throw new Error(await r.text());
    const d = await r.json();
    State.sessionId = d.session_id;
    State.sessionStart = Date.now();
    State.isRunning = true;
    onSessionStarted();
    showToast(`Session "${name}" started`, 'success');
  } catch (e) {
    showToast(`Failed to start: ${e.message}`, 'error');
  }
}

async function stopSession() {
  if (!confirm('Stop the current monitoring session?')) return;
  try {
    const r = await fetch('/api/session/stop', { method: 'POST' });
    if (!r.ok) throw new Error(await r.text());
    State.isRunning = false;
    onSessionStopped();
    showToast('Session stopped', 'info');
  } catch (e) {
    showToast(`Error: ${e.message}`, 'error');
  }
}

function onSessionStarted() {
  // Buttons
  document.getElementById('btnStart').classList.add('hidden');
  document.getElementById('btnStop').classList.remove('hidden');
  document.getElementById('btnBreak').classList.remove('hidden');

  // Video feed
  const src = `/api/stream/video?t=${Date.now()}`;
  const videoFeed = document.getElementById('videoFeed');
  videoFeed.src = src;
  videoFeed.classList.remove('hidden');
  document.getElementById('videoPlaceholder').classList.add('hidden');

  // Live badge
  document.getElementById('liveBadge').textContent  = '● LIVE';
  document.getElementById('liveBadge').classList.add('live');

  // System status
  document.getElementById('systemDot').classList.add('active');
  document.getElementById('systemStatus').textContent = 'Session Active';

  // Start session duration timer (updates every second)
  if (State.durationTimer) {
    clearInterval(State.durationTimer);
  }
  State.durationTimer = setInterval(updateSessionDuration, 1000);
  updateSessionDuration(); // Update immediately

  // Connect WebSocket
  connectWebSocket();
}

function onSessionStopped() {
  document.getElementById('btnStart').classList.remove('hidden');
  document.getElementById('btnStop').classList.add('hidden');
  document.getElementById('btnBreak').classList.add('hidden');

  const videoFeed = document.getElementById('videoFeed');
  videoFeed.src = '';
  videoFeed.classList.add('hidden');
  document.getElementById('videoPlaceholder').classList.remove('hidden');

  document.getElementById('liveBadge').textContent  = '● IDLE';
  document.getElementById('liveBadge').classList.remove('live');

  document.getElementById('systemDot').classList.remove('active');
  document.getElementById('systemStatus').textContent = 'Session Ended';

  // Stop session duration timer
  if (State.durationTimer) {
    clearInterval(State.durationTimer);
    State.durationTimer = null;
  }

  // End break if active
  if (BreakState.isOnBreak) {
    endBreak();
  }

  if (State.ws) { State.ws.close(); State.ws = null; }
  clearTimeout(State.reconnectTimer);
  loadSessions();
}

// ─── Session Duration Update ──────────────────────────────────────────────────
function updateSessionDuration() {
  if (State.sessionStart) {
    const elapsed = Math.floor((Date.now() - State.sessionStart) / 1000);
    const mm = String(Math.floor(elapsed / 60)).padStart(2, '0');
    const ss = String(elapsed % 60).padStart(2, '0');
    document.getElementById('kpiDuration').textContent = `${mm}:${ss}`;
  }
}

// ─── WebSocket ────────────────────────────────────────────────────────────────
function connectWebSocket() {
  if (State.ws) State.ws.close();
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const url = `${proto}://${location.host}/ws/metrics`;
  State.ws = new WebSocket(url);

  State.ws.onopen = () => {
    console.log('[WS] Connected');
    clearTimeout(State.reconnectTimer);
    // Send ping every 20s to keep alive
    State.ws._pingInterval = setInterval(() => {
      if (State.ws && State.ws.readyState === WebSocket.OPEN) {
        State.ws.send('ping');
      }
    }, 20000);
  };

  State.ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      State.latestData = data;
      updateDashboard(data);
    } catch (e) { /* ignore malformed */ }
  };

  State.ws.onerror = (e) => { console.warn('[WS] Error', e); };

  State.ws.onclose = () => {
    clearInterval(State.ws?._pingInterval);
    if (State.isRunning) {
      State.reconnectTimer = setTimeout(connectWebSocket, State.reconnectDelay);
    }
  };
}

// ─── Dashboard Updater ────────────────────────────────────────────────────────
function updateDashboard(data) {
  const { class_attention, student_count, fps, students } = data;

  // ── KPIs ──────────────────────────────────────────────────────────────────
  const attn = class_attention ?? 0;
  document.getElementById('kpiAttention').textContent = attn.toFixed(0);
  document.getElementById('kpiAttentionBar').style.width = `${attn}%`;
  document.getElementById('kpiStudents').textContent = student_count ?? 0;
  document.getElementById('kpiFps').textContent = (fps ?? 0).toFixed(1);

  // ── Attention History → Chart ──────────────────────────────────────────────
  State.attentionHistory.push({ t: Date.now(), v: attn });
  if (State.attentionHistory.length > State.maxHistoryPoints) {
    State.attentionHistory.shift();
  }
  updateAttentionChart();

  // ── Behaviour Breakdown ────────────────────────────────────────────────────
  const beh = { attentive: 0, raised_hand: 0, side_talk: 0, phone_usage: 0, head_down: 0, unknown: 0 };
  const emotions = {};
  const total = students?.length || 1;

  students?.forEach(s => {
    const b = s.behaviour || 'unknown';
    beh[b] = (beh[b] || 0) + 1;
    if (s.dominant_emotion) {
      emotions[s.dominant_emotion] = (emotions[s.dominant_emotion] || 0) + 1;
    }
  });

  ['attentive','raised_hand','side_talk','phone_usage','head_down'].forEach(k => {
    const cnt = beh[k] || 0;
    const el = document.getElementById(`bar-${k}`);
    const countEl = document.getElementById(`cnt-${k}`);
    if (el) el.style.width = `${(cnt / total) * 100}%`;
    if (countEl) countEl.textContent = cnt;
  });

  // ── Emotion Bars ───────────────────────────────────────────────────────────
  const emoKeys = ['neutral','happy','sad','angry','surprise','fear','disgust'];
  const maxEmo = Math.max(...emoKeys.map(k => emotions[k] || 0), 1);
  emoKeys.forEach(k => {
    const cnt = emotions[k] || 0;
    const fill = document.querySelector(`#emo-${k} .emo-fill`);
    const item = document.getElementById(`emo-${k}`);
    if (fill) {
      fill.style.height = `${(cnt / maxEmo) * 100}%`;
    }
    if (item) {
      const pct = total > 0 ? ((cnt / total) * 100).toFixed(0) : 0;
      item.title = `${k}: ${cnt} students (${pct}%)`;
    }
  });

  // ── Students Grid ──────────────────────────────────────────────────────────
  updateStudentGrid(students || []);
  updateStudentMiniList(students || []);

  // ── Alerts ─────────────────────────────────────────────────────────────────
  if (attn > 0 && attn < 35) {
    showAlert(`Low class attention detected: ${attn.toFixed(0)}%`, 'danger');
  }
}

// ─── Student Grid ─────────────────────────────────────────────────────────────
function updateStudentGrid(students) {
  const grid = document.getElementById('studentGrid');
  document.getElementById('studentCount').textContent = `${students.length} student${students.length !== 1 ? 's' : ''} in frame`;

  if (!students.length) {
    grid.innerHTML = '<div class="empty-state">No students detected in frame</div>';
    return;
  }

  grid.innerHTML = '';
  students.forEach(s => {
    const score = Math.round(s.attention_score || 0);
    const color = s.attention_color || '#64748b';
    const card = document.createElement('div');
    card.className = 'student-card';
    card.innerHTML = `
      <div class="sc-id">Student #${s.track_id}</div>
      <div class="sc-score-ring" style="border-color:${color};color:${color}">${score}</div>
      <div class="sc-label" style="color:${color}">${s.attention_label || ''}</div>
      <div class="sc-beh">📍 ${formatBehaviour(s.behaviour)}</div>
      <div class="sc-emotion">${s.dominant_emotion ? '😶 ' + s.dominant_emotion : ''}</div>
    `;
    grid.appendChild(card);
  });
}

function updateStudentMiniList(students) {
  const list = document.getElementById('studentMiniList');
  if (!students.length) {
    list.innerHTML = '<div class="empty-state">No students detected</div>';
    return;
  }
  list.innerHTML = '';
  students.forEach(s => {
    const score = Math.round(s.attention_score || 0);
    const color = s.attention_color || '#64748b';
    const item = document.createElement('div');
    item.className = 'student-mini-item';
    item.innerHTML = `
      <span class="smi-id">#${s.track_id}</span>
      <div class="smi-bar-bg"><div class="smi-bar" style="width:${score}%;background:${color}"></div></div>
      <span class="smi-score" style="color:${color}">${score}%</span>
    `;
    list.appendChild(item);
  });
}

function formatBehaviour(b) {
  const map = {
    attentive: 'Attentive', raised_hand: 'Raised Hand', side_talk: 'Side Talk',
    phone_usage: 'Phone Usage', head_down: 'Head Down', unknown: 'Unknown'
  };
  return map[b] || b;
}

// ─── Alerts (debounced) ────────────────────────────────────────────────────────
let _lastAlertTime = 0;
function showAlert(message, type = 'warning') {
  if (Date.now() - _lastAlertTime < 30000) return;
  _lastAlertTime = Date.now();

  const section = document.getElementById('alertsSection');
  const div = document.createElement('div');
  div.className = `alert-toast ${type === 'danger' ? 'danger' : ''}`;
  div.innerHTML = `<span>⚠️</span><span>${message}</span>`;
  section.prepend(div);
  if (section.children.length > 5) section.lastChild.remove();
}

// ─── Charts ────────────────────────────────────────────────────────────────────
function initCharts() {
  // Attention Timeline (pure canvas, no library)
  const canvas = document.getElementById('attentionChart');
  if (canvas) {
    const ctx = canvas.getContext('2d');
    attentionChart = { canvas, ctx };
  }

  // Load analytics charts
  loadAnalytics();
}

function updateAttentionChart() {
  if (!attentionChart) return;
  const { canvas, ctx } = attentionChart;
  const dpr = window.devicePixelRatio || 1;
  const W = canvas.offsetWidth;
  const H = canvas.offsetHeight || 120;

  canvas.width  = W * dpr;
  canvas.height = H * dpr;
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, W, H);

  const data = State.attentionHistory;
  if (data.length < 2) return;

  const pad = { t: 16, r: 16, b: 24, l: 36 };
  const gW = W - pad.l - pad.r;
  const gH = H - pad.t - pad.b;

  // Grid lines
  ctx.strokeStyle = '#E2E8F0';
  ctx.lineWidth = 1;
  [0, 25, 50, 75, 100].forEach(v => {
    const y = pad.t + gH - (v / 100) * gH;
    ctx.beginPath();
    ctx.moveTo(pad.l, y);
    ctx.lineTo(W - pad.r, y);
    ctx.stroke();
    ctx.fillStyle = '#94A3B8';
    ctx.font = '10px DM Mono, monospace';
    ctx.fillText(v, 2, y + 4);
  });

  // Attention zone highlight (60–100 = green zone)
  ctx.fillStyle = 'rgba(34,197,94,0.05)';
  ctx.fillRect(pad.l, pad.t, gW, gH * 0.4);

  // Line gradient
  const grad = ctx.createLinearGradient(0, pad.t, 0, pad.t + gH);
  grad.addColorStop(0, 'rgba(37,99,235,0.3)');
  grad.addColorStop(1, 'rgba(37,99,235,0.0)');

  const xStep = gW / (State.maxHistoryPoints - 1);

  // Fill area
  ctx.beginPath();
  ctx.moveTo(pad.l, pad.t + gH);
  data.forEach((d, i) => {
    const x = pad.l + i * xStep;
    const y = pad.t + gH - (d.v / 100) * gH;
    if (i === 0) ctx.lineTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.lineTo(pad.l + (data.length - 1) * xStep, pad.t + gH);
  ctx.closePath();
  ctx.fillStyle = grad;
  ctx.fill();

  // Line
  ctx.beginPath();
  ctx.strokeStyle = '#2563EB';
  ctx.lineWidth = 2;
  ctx.lineJoin = 'round';
  data.forEach((d, i) => {
    const x = pad.l + i * xStep;
    const y = pad.t + gH - (d.v / 100) * gH;
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();

  // Current value dot
  if (data.length) {
    const last = data[data.length - 1];
    const x = pad.l + (data.length - 1) * xStep;
    const y = pad.t + gH - (last.v / 100) * gH;
    ctx.beginPath();
    ctx.arc(x, y, 4, 0, Math.PI * 2);
    ctx.fillStyle = '#2563EB';
    ctx.fill();
    ctx.fillStyle = '#0F172A';
    ctx.font = 'bold 11px DM Sans, sans-serif';
    ctx.fillText(`${last.v.toFixed(0)}%`, x + 8, y + 4);
  }
}

function drawPlaceholderChart(canvas, title, subtitle) {
  const dpr = window.devicePixelRatio || 1;
  const W = canvas.offsetWidth || 400;
  const H = canvas.offsetHeight || 200;
  canvas.width  = W * dpr;
  canvas.height = H * dpr;
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  ctx.fillStyle = '#F8FAFC';
  ctx.fillRect(0, 0, W, H);
  ctx.fillStyle = '#CBD5E1';
  ctx.font = '13px DM Sans, sans-serif';
  ctx.textAlign = 'center';
  ctx.fillText(subtitle, W / 2, H / 2 + 6);
}

// ─── Analytics Charts ──────────────────────────────────────────────────────────
function drawDistributionChart(canvas, data) {
  const dpr = window.devicePixelRatio || 1;
  const W = canvas.offsetWidth || 400;
  const H = canvas.offsetHeight || 200;
  canvas.width = W * dpr;
  canvas.height = H * dpr;
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  
  // Clear with gradient background
  const bgGrad = ctx.createLinearGradient(0, 0, 0, H);
  bgGrad.addColorStop(0, '#FFFFFF');
  bgGrad.addColorStop(1, '#F8FAFC');
  ctx.fillStyle = bgGrad;
  ctx.fillRect(0, 0, W, H);
  
  const buckets = ['0-20', '21-40', '41-60', '61-80', '81-100'];
  const labels = ['Very Low', 'Low', 'Medium', 'Good', 'Excellent'];
  const colors = ['#EF4444', '#F59E0B', '#EAB308', '#84CC16', '#22C55E'];
  const values = buckets.map(b => data[b] || 0);
  const maxVal = Math.max(...values, 1);
  const totalStudents = values.reduce((sum, v) => sum + v, 0);
  
  const pad = { t: 20, r: 20, b: 70, l: 50 };
  const chartW = W - pad.l - pad.r;
  const chartH = H - pad.t - pad.b;
  const barWidth = chartW / buckets.length - 12;
  
  // Draw grid lines
  ctx.strokeStyle = '#E2E8F0';
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = pad.t + (chartH / 4) * i;
    ctx.beginPath();
    ctx.moveTo(pad.l, y);
    ctx.lineTo(W - pad.r, y);
    ctx.stroke();
    
    // Y-axis labels
    const val = Math.round(maxVal * (1 - i / 4));
    ctx.fillStyle = '#94A3B8';
    ctx.font = '11px DM Mono';
    ctx.textAlign = 'right';
    ctx.fillText(val.toString(), pad.l - 8, y + 4);
  }
  
  buckets.forEach((bucket, i) => {
    const val = values[i];
    const barHeight = (val / maxVal) * chartH;
    const x = pad.l + i * (barWidth + 12) + 6;
    const y = pad.t + chartH - barHeight;
    
    // Bar with gradient
    const barGrad = ctx.createLinearGradient(0, y, 0, y + barHeight);
    barGrad.addColorStop(0, colors[i]);
    barGrad.addColorStop(1, colors[i] + 'CC');
    ctx.fillStyle = barGrad;
    
    // Draw bar with rounded top
    ctx.beginPath();
    ctx.roundRect(x, y, barWidth, barHeight, [4, 4, 0, 0]);
    ctx.fill();
    
    // Add shadow
    ctx.shadowColor = 'rgba(0,0,0,0.1)';
    ctx.shadowBlur = 4;
    ctx.shadowOffsetY = 2;
    ctx.fill();
    ctx.shadowColor = 'transparent';
    
    // Value on top of bar
    if (val > 0) {
      ctx.fillStyle = '#0F172A';
      ctx.font = 'bold 14px DM Mono';
      ctx.textAlign = 'center';
      ctx.fillText(val.toString(), x + barWidth / 2, y - 8);
      
      // Percentage
      const pct = ((val / totalStudents) * 100).toFixed(0);
      ctx.fillStyle = '#64748B';
      ctx.font = '11px DM Sans';
      ctx.fillText(`${pct}%`, x + barWidth / 2, y - 22);
    }
    
    // Score range label
    ctx.fillStyle = '#475569';
    ctx.font = 'bold 11px DM Mono';
    ctx.textAlign = 'center';
    ctx.fillText(bucket, x + barWidth / 2, pad.t + chartH + 18);
    
    // Quality label
    ctx.fillStyle = colors[i];
    ctx.font = '10px DM Sans';
    ctx.fillText(labels[i], x + barWidth / 2, pad.t + chartH + 32);
  });
  
  // Y-axis label
  ctx.fillStyle = '#475569';
  ctx.font = 'bold 11px DM Sans';
  ctx.textAlign = 'center';
  ctx.save();
  ctx.translate(12, H / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.fillText('Number of Students', 0, 0);
  ctx.restore();
  
  // X-axis label
  ctx.fillStyle = '#475569';
  ctx.font = 'bold 11px DM Sans';
  ctx.textAlign = 'center';
  ctx.fillText('Attention Score Range', W / 2, H - 8);
}

function drawBehaviourTimeChart(canvas, data) {
  const dpr = window.devicePixelRatio || 1;
  const W = canvas.offsetWidth || 400;
  const H = canvas.offsetHeight || 200;
  canvas.width = W * dpr;
  canvas.height = H * dpr;
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  
  // Clear with gradient background
  const bgGrad = ctx.createLinearGradient(0, 0, 0, H);
  bgGrad.addColorStop(0, '#FFFFFF');
  bgGrad.addColorStop(1, '#F8FAFC');
  ctx.fillStyle = bgGrad;
  ctx.fillRect(0, 0, W, H);
  
  if (!data || data.length === 0) {
    ctx.fillStyle = '#CBD5E1';
    ctx.font = '14px DM Sans';
    ctx.textAlign = 'center';
    ctx.fillText('No behaviour data available', W / 2, H / 2);
    ctx.font = '12px DM Sans';
    ctx.fillStyle = '#94A3B8';
    ctx.fillText('Start a session to see behaviour patterns', W / 2, H / 2 + 20);
    return;
  }
  
  const behaviours = ['attentive', 'raised_hand', 'side_talk', 'phone_usage', 'head_down'];
  const colors = {
    attentive: '#22C55E',
    raised_hand: '#3B82F6',
    side_talk: '#F97316',
    phone_usage: '#EAB308',
    head_down: '#A855F7'
  };
  
  const labels = {
    attentive: 'Attentive',
    raised_hand: 'Raised Hand',
    side_talk: 'Side Talk',
    phone_usage: 'Phone',
    head_down: 'Head Down'
  };
  
  const pad = { t: 20, r: 20, b: 50, l: 50 };
  const chartW = W - pad.l - pad.r;
  const chartH = H - pad.t - pad.b;
  
  // Limit data points for better visualization
  const maxPoints = 20;
  const displayData = data.length > maxPoints ? 
    data.filter((_, i) => i % Math.ceil(data.length / maxPoints) === 0) : 
    data;
  
  const barWidth = Math.max(chartW / displayData.length - 4, 8);
  const barSpacing = 4;
  
  // Find max total for scaling
  const maxTotal = Math.max(...displayData.map(d => 
    behaviours.reduce((sum, b) => sum + (d[b] || 0), 0)
  ), 1);
  
  // Draw grid lines
  ctx.strokeStyle = '#E2E8F0';
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = pad.t + (chartH / 4) * i;
    ctx.beginPath();
    ctx.moveTo(pad.l, y);
    ctx.lineTo(W - pad.r, y);
    ctx.stroke();
    
    // Y-axis labels
    const val = Math.round(maxTotal * (1 - i / 4));
    ctx.fillStyle = '#94A3B8';
    ctx.font = '11px DM Mono';
    ctx.textAlign = 'right';
    ctx.fillText(val.toString(), pad.l - 8, y + 4);
  }
  
  // Draw bars
  displayData.forEach((point, i) => {
    const x = pad.l + i * (barWidth + barSpacing);
    let yOffset = pad.t + chartH;
    
    behaviours.forEach(behaviour => {
      const val = point[behaviour] || 0;
      const barHeight = (val / maxTotal) * chartH;
      
      if (barHeight > 2) {
        // Draw bar with rounded top
        ctx.fillStyle = colors[behaviour];
        ctx.beginPath();
        ctx.roundRect(x, yOffset - barHeight, barWidth, barHeight, [2, 2, 0, 0]);
        ctx.fill();
        
        // Add subtle shadow
        ctx.shadowColor = 'rgba(0,0,0,0.1)';
        ctx.shadowBlur = 2;
        ctx.shadowOffsetY = 1;
        ctx.fill();
        ctx.shadowColor = 'transparent';
        
        yOffset -= barHeight;
      }
    });
    
    // X-axis time labels (show every few bars)
    if (i % Math.max(1, Math.floor(displayData.length / 8)) === 0) {
      const time = new Date(point.timestamp);
      const timeStr = time.toLocaleTimeString('en-US', { 
        hour: '2-digit', 
        minute: '2-digit',
        hour12: false 
      });
      ctx.fillStyle = '#64748B';
      ctx.font = '10px DM Mono';
      ctx.textAlign = 'center';
      ctx.save();
      ctx.translate(x + barWidth / 2, pad.t + chartH + 12);
      ctx.rotate(-Math.PI / 6);
      ctx.fillText(timeStr, 0, 0);
      ctx.restore();
    }
  });
  
  // Y-axis label
  ctx.fillStyle = '#475569';
  ctx.font = 'bold 11px DM Sans';
  ctx.textAlign = 'center';
  ctx.save();
  ctx.translate(12, H / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.fillText('Student Count', 0, 0);
  ctx.restore();
  
  // X-axis label
  ctx.fillStyle = '#475569';
  ctx.font = 'bold 11px DM Sans';
  ctx.textAlign = 'center';
  ctx.fillText('Time', W / 2, H - 8);
}

async function loadAnalytics() {
  try {
    // Load sessions for dropdown
    const sessions = await fetch('/api/sessions').then(r => r.json());
    const selector = document.getElementById('analytics-session-selector');
    
    // Populate dropdown
    selector.innerHTML = '<option value="current">Current/Latest Session</option>';
    sessions.forEach(s => {
      const option = document.createElement('option');
      option.value = s.id;
      const date = new Date(s.started_at).toLocaleString();
      option.textContent = `${s.session_name || 'Session'} - ${date}`;
      selector.appendChild(option);
    });
    
    // Load current/latest session analytics
    await loadSelectedSessionAnalytics();
  } catch (e) {
    console.error('Failed to load analytics:', e);
  }
}

async function loadSelectedSessionAnalytics() {
  try {
    const selector = document.getElementById('analytics-session-selector');
    const selectedValue = selector.value;
    
    let data;
    if (selectedValue === 'current') {
      // Try current session first
      let r = await fetch('/api/analytics/current');
      data = await r.json();
      
      // If no active session, get most recent
      if (data.error || !data.attention_distribution) {
        const sessions = await fetch('/api/sessions').then(r => r.json());
        if (sessions.length > 0) {
          r = await fetch(`/api/analytics/session/${sessions[0].id}`);
          data = await r.json();
        }
      }
    } else {
      // Load specific session
      const r = await fetch(`/api/analytics/session/${selectedValue}`);
      data = await r.json();
    }
    
    if (!data || !data.attention_distribution) {
      showEmptyAnalytics();
      return;
    }
    
    // Update summary cards
    document.getElementById('summary-avg').textContent = `${data.avg_attention.toFixed(0)}%`;
    document.getElementById('summary-peak').textContent = `${data.peak_attention.toFixed(0)}%`;
    document.getElementById('summary-low').textContent = `${data.lowest_attention.toFixed(0)}%`;
    
    // Find dominant emotion
    const emotions = data.emotion_summary || {};
    const dominantEmotion = Object.keys(emotions).reduce((a, b) => 
      emotions[a] > emotions[b] ? a : b, Object.keys(emotions)[0] || 'neutral'
    );
    document.getElementById('summary-emotion').textContent = 
      dominantEmotion ? dominantEmotion.charAt(0).toUpperCase() + dominantEmotion.slice(1) : '—';
    
    // Draw charts
    const distCanvas = document.getElementById('distributionChart');
    const behCanvas = document.getElementById('behaviourTimeChart');
    
    if (distCanvas && data.attention_distribution) {
      drawDistributionChart(distCanvas, data.attention_distribution);
    }
    
    if (behCanvas && data.behaviour_timeline) {
      drawBehaviourTimeChart(behCanvas, data.behaviour_timeline);
    }
    
    // Show emotion breakdown
    showEmotionBreakdown(data.emotion_summary || {});
    
    // Generate insights
    generateInsights(data);
    
  } catch (e) {
    console.error('Failed to load session analytics:', e);
    showEmptyAnalytics();
  }
}

function showEmptyAnalytics() {
  document.getElementById('summary-avg').textContent = '—';
  document.getElementById('summary-peak').textContent = '—';
  document.getElementById('summary-low').textContent = '—';
  document.getElementById('summary-emotion').textContent = '—';
  document.getElementById('emotionBreakdown').innerHTML = '<p style="text-align:center;color:var(--text-muted);padding:40px;">No data available</p>';
  document.getElementById('insightsList').innerHTML = '<p style="text-align:center;color:var(--text-muted);padding:40px;">Start a session to see insights</p>';
}

function showEmotionBreakdown(emotions) {
  const container = document.getElementById('emotionBreakdown');
  const total = Object.values(emotions).reduce((sum, val) => sum + val, 0);
  
  if (total === 0) {
    container.innerHTML = '<p style="text-align:center;color:var(--text-muted);padding:40px;">No emotion data</p>';
    return;
  }
  
  const emotionColors = {
    neutral: '#94A3B8',
    happy: '#22C55E',
    sad: '#3B82F6',
    angry: '#EF4444',
    surprise: '#F59E0B',
    fear: '#A855F7',
    disgust: '#64748B'
  };
  
  let html = '';
  Object.entries(emotions).sort((a, b) => b[1] - a[1]).forEach(([emotion, count]) => {
    const percentage = ((count / total) * 100).toFixed(1);
    const color = emotionColors[emotion] || '#94A3B8';
    html += `
      <div class="emotion-bar-item">
        <div class="emotion-bar-label">
          <span>${emotion.charAt(0).toUpperCase() + emotion.slice(1)}</span>
          <span>${count} (${percentage}%)</span>
        </div>
        <div class="emotion-bar-track">
          <div class="emotion-bar-fill" style="width: ${percentage}%; background: ${color};"></div>
        </div>
      </div>
    `;
  });
  
  container.innerHTML = html;
}

function generateInsights(data) {
  const insights = [];
  
  // Attention insights
  if (data.avg_attention >= 70) {
    insights.push({ icon: '✅', text: 'Excellent class engagement! Average attention above 70%.', type: 'success' });
  } else if (data.avg_attention >= 50) {
    insights.push({ icon: '👍', text: 'Good attention levels. Consider interactive activities to boost engagement.', type: 'info' });
  } else {
    insights.push({ icon: '⚠️', text: 'Low attention detected. Try breaking content into smaller segments.', type: 'warning' });
  }
  
  // Attention variance
  const variance = data.peak_attention - data.lowest_attention;
  if (variance > 50) {
    insights.push({ icon: '📊', text: `High attention variance (${variance}%). Students may need more consistent pacing.`, type: 'info' });
  }
  
  // Behaviour insights
  const dist = data.attention_distribution;
  const lowAttention = (dist['0-20'] || 0) + (dist['21-40'] || 0);
  const highAttention = (dist['61-80'] || 0) + (dist['81-100'] || 0);
  
  if (highAttention > lowAttention * 2) {
    insights.push({ icon: '🎯', text: 'Most students maintained high attention throughout the session.', type: 'success' });
  }
  
  // Emotion insights
  const emotions = data.emotion_summary || {};
  const totalEmotions = Object.values(emotions).reduce((sum, val) => sum + val, 0);
  if (totalEmotions > 0) {
    const happyPercent = ((emotions.happy || 0) / totalEmotions) * 100;
    if (happyPercent > 40) {
      insights.push({ icon: '😊', text: 'Positive classroom atmosphere detected with high happiness levels.', type: 'success' });
    }
  }
  
  // Recommendations
  if (data.avg_attention < 60) {
    insights.push({ icon: '💡', text: 'Recommendation: Use more visual aids and interactive elements.', type: 'tip' });
  }
  
  const container = document.getElementById('insightsList');
  if (insights.length === 0) {
    container.innerHTML = '<p style="text-align:center;color:var(--text-muted);padding:40px;">No insights available</p>';
    return;
  }
  
  let html = '';
  insights.forEach(insight => {
    const colorClass = insight.type === 'success' ? 'insight-success' : 
                       insight.type === 'warning' ? 'insight-warning' : 
                       insight.type === 'tip' ? 'insight-tip' : 'insight-info';
    html += `
      <div class="insight-item ${colorClass}">
        <span class="insight-icon">${insight.icon}</span>
        <span class="insight-text">${insight.text}</span>
      </div>
    `;
  });
  
  container.innerHTML = html;
}

// ─── Sessions Table ────────────────────────────────────────────────────────────
async function loadSessions() {
  try {
    const r = await fetch('/api/sessions');
    const sessions = await r.json();
    const tbody = document.getElementById('sessionsBody');
    if (!sessions.length) {
      tbody.innerHTML = '<tr><td colspan="8" class="empty-state">No sessions recorded yet</td></tr>';
      return;
    }
    tbody.innerHTML = sessions.map(s => {
      const started = s.started_at ? new Date(s.started_at).toLocaleString() : '—';
      const dur = durationString(s.started_at, s.ended_at);
      const avg = s.avg_attention_score ? `${s.avg_attention_score.toFixed(0)}%` : '—';
      return `
        <tr>
          <td>${s.id}</td>
          <td><strong>${s.session_name || '—'}</strong></td>
          <td>${s.subject || '—'}</td>
          <td>${s.instructor || '—'}</td>
          <td>${started}</td>
          <td>${dur}</td>
          <td>${avg}</td>
          <td><span class="badge ${s.is_active ? 'badge-active' : 'badge-ended'}">${s.is_active ? 'Active' : 'Ended'}</span></td>
        </tr>
      `;
    }).join('');
  } catch (e) {
    console.warn('Could not load sessions:', e);
  }
}

function durationString(start, end) {
  if (!start) return '—';
  const s = new Date(start);
  const e = end ? new Date(end) : new Date();
  const diff = Math.floor((e - s) / 1000);
  if (diff < 0) return '—';
  const mm = Math.floor(diff / 60);
  const ss = diff % 60;
  return `${mm}m ${ss}s`;
}

// ─── Clock ─────────────────────────────────────────────────────────────────────
function startClock() {
  const el = document.getElementById('timeDisplay');
  setInterval(() => {
    el.textContent = new Date().toLocaleTimeString();
  }, 1000);
}

// ─── Toast ─────────────────────────────────────────────────────────────────────
function showToast(message, type = 'info') {
  const container = document.getElementById('toastContainer');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `<span>${message}</span>`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.transition = 'opacity .3s';
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

// ─── Timetable Functions ──────────────────────────────────────────────────────
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
  document.getElementById('ttModalTitle').textContent = 'Add Class to Timetable';
  document.getElementById('tt-id').value = '';
  document.getElementById('tt-day').value = '0';
  document.getElementById('tt-start').value = '09:00';
  document.getElementById('tt-end').value = '10:00';
  document.getElementById('tt-subject').value = '';
  document.getElementById('tt-instructor').value = '';
  document.getElementById('tt-classroom').value = '';
  document.getElementById('tt-color').value = '#3B82F6';
  document.getElementById('timetableModal').classList.remove('hidden');
}

function addTimetableEntry(dayIdx, time) {
  document.getElementById('ttModalTitle').textContent = 'Add Class to Timetable';
  document.getElementById('tt-id').value = '';
  document.getElementById('tt-day').value = dayIdx;
  document.getElementById('tt-start').value = time;
  const [h, m] = time.split(':');
  const endHour = (parseInt(h) + 1).toString().padStart(2, '0');
  document.getElementById('tt-end').value = `${endHour}:${m}`;
  document.getElementById('tt-subject').value = '';
  document.getElementById('tt-instructor').value = '';
  document.getElementById('tt-classroom').value = '';
  document.getElementById('tt-color').value = '#3B82F6';
  document.getElementById('timetableModal').classList.remove('hidden');
}

async function editTimetableEntry(id) {
  try {
    const r = await fetch('/api/timetable');
    const entries = await r.json();
    const entry = entries.find(e => e.id === id);
    if (!entry) return;
    
    document.getElementById('ttModalTitle').textContent = 'Edit Class';
    document.getElementById('tt-id').value = entry.id;
    document.getElementById('tt-day').value = entry.day_of_week;
    document.getElementById('tt-start').value = entry.start_time;
    document.getElementById('tt-end').value = entry.end_time;
    document.getElementById('tt-subject').value = entry.subject;
    document.getElementById('tt-instructor').value = entry.instructor;
    document.getElementById('tt-classroom').value = entry.classroom;
    document.getElementById('tt-color').value = entry.color_hex;
    document.getElementById('timetableModal').classList.remove('hidden');
  } catch (e) {
    showToast('Failed to load entry', 'error');
  }
}

function closeTimetableModal() {
  document.getElementById('timetableModal').classList.add('hidden');
}

async function saveTimetableEntry() {
  const id = document.getElementById('tt-id').value;
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
    let r;
    if (id) {
      // Update existing
      r = await fetch(`/api/timetable/${id}`, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(data)
      });
    } else {
      // Create new
      r = await fetch('/api/timetable', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(data)
      });
    }
    
    if (r.ok) {
      showToast(id ? 'Timetable entry updated' : 'Timetable entry added', 'success');
      closeTimetableModal();
      loadTimetable();
    } else {
      showToast('Failed to save entry', 'error');
    }
  } catch (e) {
    showToast('Failed to save entry', 'error');
  }
}

async function loadFromTimetable() {
  // This function is now replaced by loadSelectedTimetableEntry()
  // Keeping for backward compatibility but redirecting to new approach
  showToast('Please use the dropdown above to select a class', 'info');
}




// ─── Break Timer Functions ────────────────────────────────────────────────────
function showBreakModal() {
  document.getElementById('breakModal').classList.remove('hidden');
}

function closeBreakModal() {
  document.getElementById('breakModal').classList.add('hidden');
}

async function startBreak(duration) {
  closeBreakModal();
  
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
    
    // Show timer widget and overlay
    const widget = document.getElementById('breakTimer');
    const overlay = document.getElementById('breakOverlay');
    
    widget.classList.remove('hidden');
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
  const timeStr = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
  
  // Update both displays
  document.getElementById('countdownTime').textContent = timeStr;
  document.getElementById('breakOverlayTimer').textContent = timeStr;
  
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
  const overlay = document.getElementById('breakOverlay');
  
  widget.classList.add('hidden');
  overlay.classList.add('hidden');
  
  // Reset progress circle
  const circle = document.getElementById('breakProgressCircle');
  circle.style.strokeDashoffset = 283;
  
  showToast('Break ended', 'success');
}


// ─── Logout Function ──────────────────────────────────────────────────────────
function handleLogout() {
  if (confirm('Are you sure you want to logout?')) {
    localStorage.removeItem('classvision_user');
    sessionStorage.removeItem('classvision_user');
    window.location.href = '/';
  }
}
