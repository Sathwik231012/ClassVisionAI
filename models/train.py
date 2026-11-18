"""
ClassVisionAI — YOLOv8 Training Script
Fine-tunes YOLOv8n (nano) on classroom data with Apple Silicon MPS support.
Also trains a lightweight emotion CNN on FER2013.

Run: python models/train.py --task detection
     python models/train.py --task emotion
"""

import argparse
from pathlib import Path
from ultralytics import YOLO
import torch


def get_device():
    if torch.backends.mps.is_available():
        return "mps"
    elif torch.cuda.is_available():
        return "cuda"
    return "cpu"


def train_person_detector():
    """
    Fine-tune YOLOv8n for classroom person detection.
    Starts from COCO-pretrained weights — needs classroom_custom dataset.
    """
    device = get_device()
    print(f"[Train] Person Detector | Device: {device}")

    model = YOLO("yolov8n.pt")   # nano — fastest, Apple Silicon friendly

    results = model.train(
        data=str(Path(__file__).parent.parent / "data" / "classroom_custom.yaml"),
        epochs=50,
        imgsz=640,
        batch=8,                  # safe for 16GB unified memory
        device=device,
        optimizer="AdamW",
        lr0=0.001,
        cos_lr=True,
        # ── Augmentation ───────────────────────────────────────────────────
        hsv_h=0.015,              # hue variation (classroom lighting)
        hsv_s=0.5,
        hsv_v=0.4,
        degrees=5.0,              # slight rotation
        translate=0.1,
        scale=0.3,
        flipud=0.0,
        fliplr=0.5,
        mosaic=1.0,
        mixup=0.1,
        # ── Paths ─────────────────────────────────────────────────────────
        project="runs/detection",
        name="classroom_v1",
        save=True,
        plots=True,
        patience=15,
        workers=4,
    )

    best_model_path = Path("runs/detection/classroom_v1/weights/best.pt")
    print(f"\n[Train] Best model saved: {best_model_path}")
    print(f"[Train] mAP@0.5: {results.results_dict.get('metrics/mAP50(B)', 'N/A')}")
    return best_model_path


def train_emotion_model():
    """
    Train lightweight emotion CNN on FER2013.
    Uses a fine-tuned MobileNetV3 Small — runs well on MPS.
    """
    try:
        import torch
        import torch.nn as nn
        import torchvision
        from torchvision import transforms, datasets
        from torch.utils.data import DataLoader
        from pathlib import Path
    except ImportError:
        print("PyTorch not installed. Run: pip install torch torchvision")
        return

    device_str = get_device()
    device = torch.device(device_str)
    print(f"[Train] Emotion CNN | Device: {device_str}")

    fer_dir = Path("data/fer2013")
    if not (fer_dir / "train").exists():
        print("[Train] FER2013 dataset not found at data/fer2013/train/")
        print("[Train] Run: python data/prepare_datasets.py --download-fer")
        return

    EMOTION_CLASSES = ['angry', 'disgust', 'fear', 'happy', 'sad', 'surprise', 'neutral']
    NUM_CLASSES = len(EMOTION_CLASSES)

    # ── Transforms ────────────────────────────────────────────────────────
    train_tf = transforms.Compose([
        transforms.Grayscale(num_output_channels=3),
        transforms.Resize((96, 96)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomRotation(10),
        transforms.ColorJitter(brightness=0.3, contrast=0.3),
        transforms.ToTensor(),
        transforms.Normalize([0.5]*3, [0.5]*3),
    ])
    val_tf = transforms.Compose([
        transforms.Grayscale(num_output_channels=3),
        transforms.Resize((96, 96)),
        transforms.ToTensor(),
        transforms.Normalize([0.5]*3, [0.5]*3),
    ])

    train_ds = datasets.ImageFolder(fer_dir / "train", transform=train_tf)
    val_ds   = datasets.ImageFolder(fer_dir / "test",  transform=val_tf)

    train_loader = DataLoader(train_ds, batch_size=64, shuffle=True,  num_workers=4, pin_memory=True)
    val_loader   = DataLoader(val_ds,   batch_size=64, shuffle=False, num_workers=4, pin_memory=True)

    print(f"[Train] Training samples: {len(train_ds)} | Val samples: {len(val_ds)}")

    # ── Model: MobileNetV3-Small (lightweight, fast on MPS) ───────────────
    model = torchvision.models.mobilenet_v3_small(weights="IMAGENET1K_V1")
    model.classifier[-1] = nn.Linear(model.classifier[-1].in_features, NUM_CLASSES)
    model = model.to(device)

    # ── Class weights for imbalanced FER2013 ──────────────────────────────
    class_counts = [train_ds.targets.count(i) for i in range(NUM_CLASSES)]
    total = sum(class_counts)
    weights = torch.tensor([total / (NUM_CLASSES * c) for c in class_counts], dtype=torch.float).to(device)

    criterion = nn.CrossEntropyLoss(weight=weights)
    optimizer = torch.optim.AdamW(model.parameters(), lr=3e-4, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=30)

    best_acc = 0.0
    EPOCHS = 30

    for epoch in range(EPOCHS):
        # ── Train ──────────────────────────────────────────────────────────
        model.train()
        running_loss = 0.0
        correct = 0
        for imgs, labels in train_loader:
            imgs, labels = imgs.to(device), labels.to(device)
            optimizer.zero_grad()
            out = model(imgs)
            loss = criterion(out, labels)
            loss.backward()
            optimizer.step()
            running_loss += loss.item()
            correct += (out.argmax(1) == labels).sum().item()

        train_acc = correct / len(train_ds)

        # ── Validate ────────────────────────────────────────────────────────
        model.eval()
        val_correct = 0
        with torch.no_grad():
            for imgs, labels in val_loader:
                imgs, labels = imgs.to(device), labels.to(device)
                out = model(imgs)
                val_correct += (out.argmax(1) == labels).sum().item()

        val_acc = val_correct / len(val_ds)
        scheduler.step()

        print(f"[Epoch {epoch+1:02d}/{EPOCHS}] Loss: {running_loss/len(train_loader):.4f} | Train Acc: {train_acc:.3f} | Val Acc: {val_acc:.3f}")

        if val_acc > best_acc:
            best_acc = val_acc
            save_path = Path("models/emotion_mobilenetv3_best.pt")
            save_path.parent.mkdir(exist_ok=True)
            torch.save(model.state_dict(), save_path)
            print(f"  ✓ Best model saved (val_acc={val_acc:.3f})")

    print(f"\n[Train] Emotion training complete. Best val accuracy: {best_acc:.4f}")
    print(f"[Train] Model saved to: models/emotion_mobilenetv3_best.pt")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ClassVisionAI Training")
    parser.add_argument("--task", choices=["detection", "emotion", "all"], default="all")
    args = parser.parse_args()

    if args.task in ["detection", "all"]:
        train_person_detector()
    if args.task in ["emotion", "all"]:
        train_emotion_model()
