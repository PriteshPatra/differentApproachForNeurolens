import os
import cv2
import base64
import numpy as np
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from ultralytics import YOLO

from voice import detect_voice_emotion  # NEW

# ─── Paths ──────────────────────────────────────────────────────────────────
BASE_PATH = os.path.dirname(os.path.abspath(__file__))

MODEL_PATH = os.environ.get(
    "MODEL_PATH",
    os.path.join(BASE_PATH, "..", "runs", "detect", "emotion_model_train", "weights", "best.pt")
)

if os.path.exists("/app/runs/detect/emotion_model_train/weights/best.pt"):
    MODEL_PATH = "/app/runs/detect/emotion_model_train/weights/best.pt"

# ─── Emotion → Stress Mapping ───────────────────────────────────────────────
STRESS_MAPPING: dict[str, int] = {
    "Happy": 0,
    "Neutral": 10,
    "Surprise": 60,
    "Sad": 75,
    "Contempt": 80,
    "Disgust": 85,
    "Fear": 95,
    "Anger": 100,
    "N/A": 0,
}

EMOTION_COLOR: dict[str, str] = {
    "Happy": "#22c55e",
    "Neutral": "#6366f1",
    "Surprise": "#f59e0b",
    "Sad": "#3b82f6",
    "Contempt": "#8b5cf6",
    "Disgust": "#ef4444",
    "Fear": "#f97316",
    "Anger": "#dc2626",
    "N/A": "#6b7280",
}

CLASS_NAMES = {
    0: "Anger",
    1: "Contempt",
    2: "Disgust",
    3: "Fear",
    4: "Happy",
    5: "Neutral",
    6: "Sad",
    7: "Surprise",
}

# ─── Model ──────────────────────────────────────────────────────────────────
model: Optional[YOLO] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global model
    model_abs = os.path.abspath(MODEL_PATH)

    if not os.path.exists(model_abs):
        raise RuntimeError(f"Model not found at: {model_abs}")

    model = YOLO(model_abs)
    model.model.names = CLASS_NAMES

    print(f"✅ YOLO model loaded from: {model_abs}")

    yield

    model = None


# ─── App ────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Neurolens API",
    description="Real-Time Stress Detection & Mitigation — REST API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Request / Response Models ───────────────────────────────────────────────
class PredictRequest(BaseModel):
    image: str
    confidence: float = 0.6


class PredictResponse(BaseModel):
    emotion: str
    stress_level: int
    confidence: float
    emotion_color: str
    annotated_image: str


class VoiceRequest(BaseModel):
    audio: str  # base64 encoded audio


class BrightnessRequest(BaseModel):
    stress_level: int
    min_brightness: int = 30
    max_brightness: int = 100
    smoothing_factor: float = 0.1
    current_brightness: float = 100.0
    
    def model_post_init(self, __context):
        if self.min_brightness >= self.max_brightness:
            raise ValueError("min_brightness must be less than max_brightness")
        if not 0 <= self.stress_level <= 100:
            raise ValueError("stress_level must be between 0 and 100")


class BrightnessResponse(BaseModel):
    target_brightness: int
    new_brightness: float


class NotifyRequest(BaseModel):
    title: str
    message: str


# ─── Helpers ────────────────────────────────────────────────────────────────
def decode_image(b64: str) -> np.ndarray:
    if "," in b64:
        b64 = b64.split(",", 1)[1]

    raw = base64.b64decode(b64)
    buf = np.frombuffer(raw, dtype=np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)

    if img is None:
        raise ValueError("Could not decode image")

    return img


def encode_image(img: np.ndarray) -> str:
    _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return base64.b64encode(buf.tobytes()).decode("utf-8")


def decode_audio(b64: str, save_path="temp_audio.wav") -> str:
    if "," in b64:
        b64 = b64.split(",", 1)[1]

    raw = base64.b64decode(b64)

    with open(save_path, "wb") as f:
        f.write(raw)

    return save_path


import os_brightness
import os_notifier

# ─── Routes ─────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok", "model_loaded": model is not None}


@app.post("/api/predict", response_model=PredictResponse)
def predict(req: PredictRequest):

    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    try:
        img = decode_image(req.image)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid image: {e}")

    img_resized = cv2.resize(img, (640, 480))
    results = model.predict(source=img_resized, verbose=False, conf=req.confidence)

    emotion_label = "N/A"
    stress_level = 0
    confidence_val = 0.0

    if results[0].boxes and len(results[0].boxes):
        boxes = results[0].boxes
        best_idx = int(boxes.conf.argmax())
        box = boxes[best_idx]

        emotion_label = CLASS_NAMES[int(box.cls[0])]
        confidence_val = float(box.conf[0])
        stress_level = STRESS_MAPPING.get(emotion_label, 10)

    return PredictResponse(
        emotion=emotion_label,
        stress_level=stress_level,
        confidence=confidence_val,
        emotion_color=EMOTION_COLOR.get(emotion_label, "#6b7280"),
        annotated_image="",
    )


# ─── Voice Emotion Detection ────────────────────────────────────────────────
@app.post("/api/voice")
def detect_voice(req: VoiceRequest):

    try:
        audio_path = decode_audio(req.audio)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid audio payload: {e}")

    emotion, confidence = detect_voice_emotion(audio_path)

    stress_level = STRESS_MAPPING.get(emotion, 10)

    return {
        "emotion": emotion,
        "stress_level": stress_level,
        "confidence": confidence
    }


# ─── Brightness Control ─────────────────────────────────────────────────────
@app.post("/api/brightness", response_model=BrightnessResponse)
def compute_brightness(req: BrightnessRequest):

    target = req.max_brightness - (req.stress_level / 100) * (
        req.max_brightness - req.min_brightness
    )

    new_brightness = (
        (1 - req.smoothing_factor) * req.current_brightness
        + req.smoothing_factor * target
    )

    final_target = int(round(target))

    os_brightness.set_brightness(final_target)

    return BrightnessResponse(
        target_brightness=final_target,
        new_brightness=round(new_brightness, 2),
    )


# ─── Notification System ────────────────────────────────────────────────────
@app.post("/api/notify")
def trigger_notification(req: NotifyRequest):

    os_notifier.send_notification(req.title, req.message)

    return {"status": "sent"}


# ─── Emotion Metadata ───────────────────────────────────────────────────────
@app.get("/api/emotions")
def get_emotions():

    return {
        "emotions": [
            {
                "name": name,
                "stress_level": STRESS_MAPPING[name],
                "color": EMOTION_COLOR[name],
            }
            for name in CLASS_NAMES.values()
        ]
    }