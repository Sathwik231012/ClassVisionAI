"""
ClassVisionAI — Dataset Preparation Script
Downloads and prepares the best open datasets for training:

1. DAiSEE    — Student engagement labels (engagement, boredom, confusion, frustration)
2. AffectNet — Emotion recognition (450k images, 7 classes)
3. WIDER FACE / COCO — Person detection (for YOLOv8 fine-tuning)
4. CelebA    — Face attribute dataset for gaze augmentation

Run: python data/prepare_datasets.py
"""

import os
import sys
import zipfile
import tarfile
import urllib.request
from pathlib import Path

DATA_DIR = Path(__file__).parent
print(f"[Dataset Prep] Working directory: {DATA_DIR}")

# ─── DAiSEE Dataset Instructions ─────────────────────────────────────────────
print("""
╔══════════════════════════════════════════════════════════════╗
║  ClassVisionAI — Dataset Setup Guide                        ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  DATASET 1: DAiSEE (Primary — Student Engagement)           ║
║  ─────────────────────────────────────────────────────────── ║
║  URL: https://iith.ac.in/~daisee-dataset/                   ║
║  Size: ~16 GB                                               ║
║  Labels: engagement, boredom, confusion, frustration        ║
║  Used for: attention level classification                   ║
║                                                              ║
║  Steps:                                                      ║
║  1. Register at the above URL                               ║
║  2. Download all .zip files to: data/daisee/                ║
║  3. Run: python data/prepare_datasets.py --extract daisee   ║
║                                                              ║
║  DATASET 2: FER-2013 (Emotion Recognition — Kaggle)         ║
║  ─────────────────────────────────────────────────────────── ║
║  URL: https://www.kaggle.com/datasets/msambare/fer2013      ║
║  Size: ~60 MB                                               ║
║  Labels: angry, disgust, fear, happy, sad, surprise, neutral║
║  Install kaggle CLI: pip install kaggle                     ║
║  Command: kaggle datasets download msambare/fer2013         ║
║  Extract to: data/fer2013/                                  ║
║                                                              ║
║  DATASET 3: AffectNet (Best Emotion Dataset)                ║
║  ─────────────────────────────────────────────────────────── ║
║  URL: http://mohammadmahoor.com/affectnet/                  ║
║  Size: ~450k images                                         ║
║  Labels: 8 discrete emotions + valence/arousal              ║
║  Requires: academic request form submission                 ║
║                                                              ║
║  DATASET 4: COCO (Person Detection — Auto downloaded)       ║
║  ─────────────────────────────────────────────────────────── ║
║  YOLOv8 downloads this automatically when training          ║
║  person class detection model.                              ║
║                                                              ║
║  DATASET 5: Roboflow Classroom Dataset                      ║
║  ─────────────────────────────────────────────────────────── ║
║  URL: https://universe.roboflow.com/                        ║
║  Search: "classroom students" or "student pose"             ║
║  Download as: YOLOv8 format                                 ║
║  Extract to: data/classroom_custom/                         ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
""")


def download_fer2013_via_kaggle():
    """Download FER2013 dataset using Kaggle API."""
    try:
        import kaggle
        print("[Dataset] Downloading FER2013 from Kaggle...")
        fer_dir = DATA_DIR / "fer2013"
        fer_dir.mkdir(exist_ok=True)
        os.system(f"kaggle datasets download msambare/fer2013 -p {fer_dir} --unzip")
        print(f"[Dataset] FER2013 downloaded to {fer_dir}")
    except ImportError:
        print("[Dataset] kaggle not installed. Run: pip install kaggle")
        print("[Dataset] Also set KAGGLE_USERNAME and KAGGLE_KEY env vars.")


def create_dataset_config():
    """Create YAML config file for YOLOv8 classroom fine-tuning."""
    yaml_content = """
# ClassVisionAI — YOLOv8 Custom Dataset Config
# For fine-tuning on classroom person detection

path: ./data/classroom_custom   # dataset root
train: images/train
val: images/val
test: images/test

nc: 1  # number of classes
names: ['person']

# Augmentation settings for classroom variety
# (Set in ultralytics training args)
"""
    config_path = DATA_DIR / "classroom_custom.yaml"
    config_path.write_text(yaml_content.strip())
    print(f"[Dataset] Created dataset config: {config_path}")


def create_directory_structure():
    """Create all required dataset directories."""
    dirs = [
        "daisee/train", "daisee/val", "daisee/test",
        "fer2013/train", "fer2013/test",
        "affectnet/train", "affectnet/val",
        "classroom_custom/images/train",
        "classroom_custom/images/val",
        "classroom_custom/labels/train",
        "classroom_custom/labels/val",
    ]
    for d in dirs:
        (DATA_DIR / d).mkdir(parents=True, exist_ok=True)
    print("[Dataset] Directory structure created.")


if __name__ == "__main__":
    create_directory_structure()
    create_dataset_config()

    if "--download-fer" in sys.argv:
        download_fer2013_via_kaggle()
    else:
        print("\n[Dataset] Directory structure ready.")
        print("[Dataset] Follow the instructions above to download datasets.")
        print("[Dataset] Use --download-fer to auto-download FER2013 via Kaggle API.")
