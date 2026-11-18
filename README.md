# ClassVisionAI - Smart Classroom Monitoring System

> AI-powered real-time student attention and behaviour analysis system with a premium dark "Academic Observatory" theme.

## 🚀 Quick Start

### Prerequisites
- Python 3.11 (Python 3.13 is not supported — MediaPipe 0.10.18 has no 3.13 build)
- Webcam/Camera
- macOS (with MPS support) or Linux/Windows

### Installation & Setup

1. **Clone or navigate to the project directory**
```bash
cd ClassVisionAI
```

2. **Create and activate virtual environment**
```bash
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

4. **Configure environment**
```bash
cp .env.example .env      # On Windows: copy .env.example .env
# DEVICE=auto picks Apple GPU (mps), NVIDIA GPU (cuda) or CPU automatically
```

5. **Run the application**
```bash
python main.py
```

### Windows (PowerShell) quick reference
```powershell
py -3.11 -m venv venv
venv\Scripts\activate          # if blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
python -m pip install --upgrade pip
pip install -r requirements.txt
copy .env.example .env
python main.py
```

6. **Access the application**
- Open browser: http://localhost:8000
- Login credentials:
  - Username: `teacher`
  - Password: `demo123`

## 📋 System Requirements

### Python Packages
- FastAPI (web framework)
- Uvicorn (ASGI server)
- OpenCV (computer vision)
- TensorFlow/Keras (deep learning)
- MediaPipe (pose estimation)
- DeepFace (emotion analysis)
- YOLO (object detection)
- DeepSORT (object tracking)
- SQLAlchemy (database)
- NumPy, Pandas (data processing)

### Hardware
- **Camera**: Built-in webcam or external USB camera
- **GPU**: Optional but recommended (MPS for Apple Silicon, CUDA for NVIDIA)
- **RAM**: Minimum 8GB, recommended 16GB+
- **CPU**: Multi-core processor recommended

## 🎨 Features

### Core Functionality
- ✅ **Real-time Video Monitoring** - Live classroom feed with AI annotations
- ✅ **Attention Tracking** - Individual and class-wide attention scoring
- ✅ **Behaviour Detection** - Identifies attentive, raised hand, side talk, phone usage, head down
- ✅ **Emotion Analysis** - Detects 7 emotions (neutral, happy, sad, angry, surprise, fear, disgust)
- ✅ **Student Tracking** - Multi-object tracking with unique IDs
- ✅ **Session Management** - Start/stop monitoring sessions with metadata
- ✅ **Analytics Dashboard** - Comprehensive charts and insights
- ✅ **Timetable Integration** - Weekly class schedule management
- ✅ **Break Timer** - Attention-adaptive Pomodoro-style breaks
- ✅ **Session History** - View past sessions and analytics

### UI/UX Features
- 🌙 **Dark Theme** - Premium "Academic Observatory" design
- ✨ **Glassmorphism** - Modern frosted glass effects
- 🎭 **Animations** - Smooth transitions and hover effects
- 📱 **Responsive** - Works on desktop, tablet, and mobile
- 🔐 **Authentication** - Secure login system
- 🎨 **Color-Coded** - Visual indicators for different states

## 🎯 How to Use

### 1. Login
- Navigate to http://localhost:8000
- Enter credentials: `teacher` / `demo123`
- You'll be redirected to the main dashboard

### 2. Start a Session
- Click "Start Session" button in the top bar
- Fill in session details (name, subject, instructor)
- Optionally load from timetable
- Click "Start Session" to begin monitoring

### 3. Monitor Classroom
- **Dashboard**: View real-time metrics and video feed
- **Students**: See individual student cards with attention scores
- **Analytics**: View charts and insights
- **Sessions**: Browse session history
- **Timetable**: Manage weekly class schedule

### 4. Use Break Timer
- Click "Start Break" during an active session
- Choose duration (5, 10, or 15 minutes)
- Timer appears in bottom-right corner
- Full-screen overlay available
- Click "End Break" to resume

### 5. Stop Session
- Click "Stop Session" button
- Session data is saved to database
- Analytics become available for review

## 📊 Dashboard Overview

### KPI Cards (Top Row)
1. **Class Attention** - Average attention score with progress bar
2. **Students Detected** - Number of students in frame
3. **Processing FPS** - Real-time processing speed
4. **Session Duration** - Elapsed time in mm:ss format

### Main Grid
- **Live Classroom Feed** - Annotated video stream
- **Behaviour Breakdown** - Color-coded horizontal bars
- **Attention Timeline** - 60-second rolling chart
- **Emotion Distribution** - Vertical bar chart

### Behaviour Colors
- 🟢 **Attentive** - Green
- 🔵 **Raised Hand** - Blue
- 🟠 **Side Talk** - Orange
- 🔴 **Phone Usage** - Red
- 🟣 **Head Down** - Purple

## 🎨 Theme & Design

### Color Palette
```
Background:     #080F1E  (Very dark navy)
Surface:        rgba(255,255,255,0.06)  (Glass)
Blue Accent:    #2563EB  (Electric blue)
Text:           #F0F6FF  (Light blue-white)
Green:          #22C55E  (Success)
Amber:          #F59E0B  (Warning)
Rose:           #EF4444  (Error)
```

### Design Elements
- **Glassmorphism** - Frosted glass cards with backdrop blur
- **Blue Glow** - Shadows and highlights with electric blue
- **Gradients** - Smooth color transitions on buttons and bars
- **Animations** - 0.2s transitions, smooth hover effects
- **Typography** - Playfair Display (headings), DM Sans (body), DM Mono (data)

## 🗂️ Project Structure

```
ClassVisionAI/
├── backend/
│   ├── app.py              # FastAPI application & routes
│   ├── database.py         # SQLAlchemy models & DB setup
│   ├── pipeline.py         # Main processing pipeline
│   ├── analytics.py        # Analytics data aggregation
│   └── break_advisor.py    # Break recommendation logic
├── frontend/
│   ├── index.html          # Main application UI
│   ├── login.html          # Login page
│   ├── style.css           # Main application styles
│   ├── app.js              # Frontend JavaScript logic
│   ├── login.js            # Login authentication
│   └── login.css           # Login page styles (unused, embedded)
├── models/
│   ├── behaviour_classifier.py  # Behaviour detection
│   ├── emotion_analyzer.py      # Emotion recognition
│   ├── head_pose.py             # Head pose estimation
│   └── train.py                 # Model training scripts
├── utils/
│   └── attention_engine.py      # Attention scoring logic
├── configs/
│   └── config.py           # Configuration settings
├── data/
│   └── prepare_datasets.py # Dataset preparation
├── templates/
│   ├── break_advisor_template.py
│   └── timetable_template.py
├── main.py                 # Application entry point
├── requirements.txt        # Python dependencies
├── .env.example           # Environment variables template
├── .env                   # Environment configuration (create from .env.example)
├── classvision.db         # SQLite database (auto-created)
├── yolov8n.pt            # YOLO model weights
└── README.md             # This file
```

## 🔧 Configuration

### Environment Variables (.env)
```bash
# Camera Settings
CAMERA_INDEX=0              # Camera device index
FRAME_WIDTH=1280           # Video frame width
FRAME_HEIGHT=720           # Video frame height
TARGET_FPS=30              # Target processing FPS

# Model Settings
YOLO_MODEL=yolov8n.pt      # YOLO model path
CONFIDENCE_THRESHOLD=0.5    # Detection confidence
IOU_THRESHOLD=0.4          # IoU threshold

# Database
DATABASE_URL=sqlite+aiosqlite:///./classvision.db

# Server
HOST=0.0.0.0
PORT=8000
```

## 🎓 AI Models Used

1. **YOLOv8** - Object detection for person detection
2. **DeepSORT** - Multi-object tracking
3. **MediaPipe** - Pose estimation and landmark detection
4. **DeepFace** - Facial emotion recognition
5. **Custom Behaviour Classifier** - Behaviour pattern recognition
6. **Attention Engine** - Attention score calculation

## 📈 Analytics Features

### Session Analytics
- **Attention Distribution** - 5 buckets (0-20, 21-40, 41-60, 61-80, 81-100)
- **Attention Timeline** - Time-series data with 5-second intervals
- **Behaviour Timeline** - Behaviour counts over time
- **Emotion Summary** - Aggregated emotion counts
- **Peak/Lowest/Average** - Attention statistics

### Insights Generation
- ✅ Success indicators (high engagement)
- ⚠️ Warning indicators (low attention)
- 💡 Tips and recommendations
- 📊 Data-driven observations

## 🔐 Authentication

### Current Implementation
- **Type**: Client-side demo authentication
- **Storage**: localStorage (Remember me) or sessionStorage
- **Credentials**: teacher / demo123
- **Routes**: 
  - `/` - Login page
  - `/app` - Main application (protected)

### Future Enhancements
- Backend JWT authentication
- User management system
- Role-based access (Admin, Teacher, Student)
- Password reset functionality
- Multi-user support

## 📱 Responsive Design

### Breakpoints
- **Desktop**: >1024px - Full layout with sidebar
- **Tablet**: 768-1024px - Adjusted layout
- **Mobile**: <768px - Stacked layout, collapsible sidebar
- **Small**: <480px - Compact, touch-friendly

### Mobile Features
- Collapsible sidebar
- Stacked KPI cards
- Single-column grids
- Touch-friendly buttons
- Optimized spacing

## 🐛 Troubleshooting

### Camera Not Working
```bash
# Check camera index
ls /dev/video*  # Linux
# Try different CAMERA_INDEX values in .env (0, 1, 2, etc.)
```

### Dependencies Issues
```bash
# Reinstall dependencies
pip install --upgrade pip
pip install --force-reinstall -r requirements.txt
```

### Database Issues
```bash
# Delete and recreate database
rm classvision.db
python main.py  # Will auto-create new database
```

### Theme Not Loading
```bash
# Clear browser cache
# Press Ctrl+Shift+R (Windows/Linux) or Cmd+Shift+R (Mac)
# Or use Incognito/Private window
```

### Port Already in Use
```bash
# Change PORT in .env to different value (e.g., 8001)
# Or kill process using port 8000
lsof -ti:8000 | xargs kill -9  # macOS/Linux
```

## 🚀 Performance Tips

1. **GPU Acceleration**: Use MPS (Apple Silicon) or CUDA (NVIDIA) for faster processing
2. **Lower Resolution**: Reduce FRAME_WIDTH and FRAME_HEIGHT for better FPS
3. **Adjust FPS**: Lower TARGET_FPS if system is struggling
4. **Close Other Apps**: Free up system resources
5. **Use Wired Camera**: USB cameras often perform better than built-in

## 📝 API Endpoints

### Session Management
- `POST /api/session/start` - Start monitoring session
- `POST /api/session/stop` - Stop current session
- `GET /api/session/status` - Get current session status
- `GET /api/sessions` - List all sessions

### Analytics
- `GET /api/analytics/session/{id}` - Get session analytics
- `GET /api/analytics/current` - Get current session analytics

### Timetable
- `POST /api/timetable` - Create timetable entry
- `GET /api/timetable` - List all entries
- `PUT /api/timetable/{id}` - Update entry
- `DELETE /api/timetable/{id}` - Delete entry
- `GET /api/timetable/now` - Get current class

### Break Timer
- `POST /api/break/acknowledge` - Acknowledge break

### Streaming
- `GET /api/stream/video` - MJPEG video stream
- `WS /ws/metrics` - WebSocket for real-time metrics

## 🎯 Future Enhancements

### Planned Features
- [ ] Multi-camera support
- [ ] Cloud storage integration
- [ ] Advanced analytics with ML insights
- [ ] Parent/student portals
- [ ] Mobile app
- [ ] Export reports (PDF, CSV)
- [ ] Integration with LMS systems
- [ ] Attendance tracking
- [ ] Automated alerts
- [ ] Theme customization

### AI Improvements
- [ ] Improved behaviour detection accuracy
- [ ] Engagement prediction
- [ ] Personalized recommendations
- [ ] Anomaly detection
- [ ] Attention pattern analysis

## 📄 License

This project is for educational and research purposes.

## 🙏 Acknowledgments

- **YOLOv8** by Ultralytics
- **DeepFace** by serengil
- **MediaPipe** by Google
- **FastAPI** by Sebastián Ramírez
- **TensorFlow** by Google

## 📞 Support

For issues, questions, or contributions:
1. Check the troubleshooting section
2. Review the documentation
3. Check console logs for errors
4. Verify all dependencies are installed

## 🎉 Credits

**ClassVisionAI** - Smart Classroom Monitoring System
- **Theme**: Academic Observatory (Dark)
- **Design**: Premium glassmorphism with electric blue accents
- **Built with**: Python, FastAPI, TensorFlow, OpenCV, React-like vanilla JS
- **Version**: 1.0.0
- **Year**: 2026

---

**Enjoy monitoring your classroom with AI! 🚀📚**
