"""
ClassVisionAI — Entry Point
Run with: python main.py
Or:        uvicorn main:app --reload
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import uvicorn
from backend.app import app
from configs.config import config

if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════╗
║          ClassVisionAI  —  Smart Classroom Monitor       ║
║          Student Attention & Behaviour Analysis          ║
╠══════════════════════════════════════════════════════════╣
║  Open: http://localhost:8000                             ║
║  API:  http://localhost:8000/docs                        ║
║  WS:   ws://localhost:8000/ws/metrics                    ║
╚══════════════════════════════════════════════════════════╝
    """)
    uvicorn.run(
        "backend.app:app",
        host=config.HOST,
        port=config.PORT,
        reload=config.DEBUG,
        log_level="info",
    )
