import os
import time
import queue
import threading
import tkinter as tk
import cv2
import av
import numpy as np
import streamlit as st
import screen_brightness_control as sbc
import collections
from ultralytics import YOLO
from streamlit_webrtc import webrtc_streamer

# ==========================================
# --- CONFIGURATION & CONSTANTS ---
# ==========================================
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
LOGO_PATH = os.path.join(BASE_PATH, "logo.png")
MODEL_PATH = os.path.join(BASE_PATH, "runs", "detect", "emotion_model_train", "weights", "best.pt")

STRESS_MAPPING = {
    "Happy": 0, "Neutral": 10, "Surprise": 60,
    "Sad": 75, "Contempt": 80, "Disgust": 85,
    "Fear": 95, "Anger": 100, "N/A": 0
}

# Default configuration values
DEFAULT_MIN_BRIGHTNESS = 30
DEFAULT_MAX_BRIGHTNESS = 100
DEFAULT_SMOOTHING_FACTOR = 0.1
DEFAULT_STRESS_THRESHOLD = 80
DEFAULT_NOTIFICATION_COOLDOWN = 10

# Global variables for callback thread
prediction_history = collections.deque(maxlen=20)  # Increased for more stability
current_brightness = 100
last_notification_time = 0

# Queue for thread-safe communication
results_queue = queue.Queue(maxsize=10)

# Thread lock for session state
state_lock = threading.Lock()


# ==========================================
# --- SETUP & HELPER FUNCTIONS ---
# ==========================================

def setup_page():
    """Configures the Streamlit page settings."""
    st.set_page_config(
        page_title="Stress Detection System",
        page_icon="🧠",
        layout="wide",
        initial_sidebar_state="expanded"
    )

def initialize_session_state():
    """Initializes all necessary session state variables."""
    default_values = {
        "current_brightness": 100,
        "last_notification_time": 0,
        "stress_history_chart": collections.deque(maxlen=100),
        "full_stress_history_session": [],
        "prediction_history": collections.deque(maxlen=10),  
        "min_brightness": DEFAULT_MIN_BRIGHTNESS,
        "max_brightness": DEFAULT_MAX_BRIGHTNESS,
        "smoothing_factor": DEFAULT_SMOOTHING_FACTOR,
        "stress_threshold": DEFAULT_STRESS_THRESHOLD,
        "notification_cooldown": DEFAULT_NOTIFICATION_COOLDOWN
    }
    for key, value in default_values.items():
        if key not in st.session_state:
            st.session_state[key] = value

@st.cache_resource
def load_model():
    """Loads and caches the YOLO model."""
    try:
        model = YOLO(MODEL_PATH)
        model.model.names = {
            0: "Anger", 1: "Contempt", 2: "Disgust", 3: "Fear",
            4: "Happy", 5: "Neutral", 6: "Sad", 7: "Surprise"
        }
        return model
    except Exception as e:
        st.error(f"Error loading model: {e}")
        return None

def show_warning_notification():
    """Displays a non-blocking pop-up warning using Tkinter."""
    def _popup():
        try:
            root = tk.Tk()
            root.withdraw()
            
            popup = tk.Toplevel(root)
            popup.overrideredirect(True)
            popup.attributes('-topmost', True)
            
            w, h = 400, 200
            x = (popup.winfo_screenwidth() // 2) - (w // 2)
            y = (popup.winfo_screenheight() // 2) - (h // 2)
            popup.geometry(f"{w}x{h}+{x}+{y}")
            
            label = tk.Label(
                popup,
                text="⚠️ High Stress Detected! ⚠️\nConsider taking a short break.",
                font=("Arial", 16, "bold"),
                bg="red", fg="white", padx=20, pady=20
            )
            label.pack(expand=True, fill="both")
            
            popup.after(3000, lambda: [popup.destroy(), root.destroy()])
            root.mainloop()
        except Exception:
            pass

    threading.Thread(target=_popup, daemon=True).start()


# ==========================================
# --- CORE LOGIC (WEBCAM CALLBACK) ---
# ==========================================

def video_frame_callback(frame: av.VideoFrame) -> av.VideoFrame:
    """Processes video frames for emotion detection."""
    global model, prediction_history, current_brightness, last_notification_time
    
    if model is None:
        return frame
    
    try:
        img = frame.to_ndarray(format="bgr24")
        img_resized = cv2.resize(img, (640, 480))

        results = model.predict(source=img_resized, verbose=False, conf=0.15, iou=0.5, max_det=1)
        annotated_frame = results[0].plot()

        emotion_label, stress_level, confidence = "N/A", 0, 0.0

        if results[0].boxes and len(results[0].boxes) > 0:
            box = results[0].boxes[0]
            cls_id = int(box.cls[0])
            confidence = float(box.conf[0])
            raw_emotion_label = model.model.names[cls_id]
            
            # DEBUG: Print raw detection
            print(f"Detected: {raw_emotion_label} (conf: {confidence:.2f})")

            with state_lock:
                prediction_history.append(raw_emotion_label)
                # Use most common emotion from last 20 frames for stability
                if len(prediction_history) >= 5:
                    emotion_label = collections.Counter(prediction_history).most_common(1)[0][0]
                else:
                    emotion_label = raw_emotion_label
            
            stress_level = STRESS_MAPPING.get(emotion_label, 10)

            with state_lock:
                min_bright = DEFAULT_MIN_BRIGHTNESS
                max_bright = DEFAULT_MAX_BRIGHTNESS
                smooth_factor = DEFAULT_SMOOTHING_FACTOR
                
                target_brightness = max_bright - (stress_level / 100) * (max_bright - min_bright)
                current_brightness = (1 - smooth_factor) * current_brightness + smooth_factor * target_brightness
            
            try:
                sbc.set_brightness(int(current_brightness))
            except Exception:
                pass

            with state_lock:
                current_time = time.time()
                if stress_level >= DEFAULT_STRESS_THRESHOLD:
                    if (current_time - last_notification_time > DEFAULT_NOTIFICATION_COOLDOWN):
                        show_warning_notification()
                        last_notification_time = current_time
        else:
            with state_lock:
                prediction_history.clear()

        # Send data to UI thread (non-blocking)
        try:
            results_queue.put_nowait({
                "emotion": emotion_label,
                "stress": stress_level,
                "confidence": confidence
            })
        except queue.Full:
            pass  # Skip if queue is full

        return av.VideoFrame.from_ndarray(annotated_frame, format="bgr24")

    except Exception as e:
        print(f"Callback Error: {e}")
        return frame


# ==========================================
# --- UI UPDATE FUNCTION ---
# ==========================================

def update_ui(emotion_metric, status_alert, stress_bar, chart_display, avg_metric, peak_metric):
    """Updates UI elements with latest data from queue."""
    try:
        result = results_queue.get_nowait()
        stress = result["stress"]
        emotion = result["emotion"]
        conf = result["confidence"]

        # Update emotion metric
        conf_txt = f"{conf:.2f} Conf." if emotion != "N/A" else ""
        emotion_metric.metric("Detected Emotion", emotion, delta=conf_txt)

        # Update status alert
        if stress < 40:
            status_alert.success(f"✔️ Status: Calm ({stress}%)")
        elif 40 <= stress < 75:
            status_alert.warning(f"⚠️ Status: Moderate ({stress}%)")
        else:
            status_alert.error(f"🚨 Status: High Stress ({stress}%)")

        # Update progress bar (convert to 0-1 range)
        stress_bar.progress(min(stress / 100, 1.0))

        # Update live chart
        st.session_state.stress_history_chart.append(stress)
        chart_display.line_chart(list(st.session_state.stress_history_chart))

        # Update session analytics
        st.session_state.full_stress_history_session.append(stress)
        if len(st.session_state.full_stress_history_session) > 0:
            avg_stress = np.mean(st.session_state.full_stress_history_session)
            peak_stress = np.max(st.session_state.full_stress_history_session)
            avg_metric.metric("Avg Stress", f"{avg_stress:.1f}%")
            peak_metric.metric("Peak Stress", f"{peak_stress}%")

    except queue.Empty:
        pass  # No new data available


# ==========================================
# --- MAIN APPLICATION EXECUTION ---
# ==========================================

# Initialize
setup_page()
initialize_session_state()

# Load model globally
if 'model' not in st.session_state:
    st.session_state.model = load_model()
model = st.session_state.model

# Check if model loaded successfully
if model is None:
    st.error("Failed to load model. Please check the model path and try again.")
    st.stop()

# Sidebar Configuration
st.sidebar.title("System Configuration")
if os.path.exists(LOGO_PATH):
    st.sidebar.image(LOGO_PATH, width=150)

st.session_state.min_brightness = st.sidebar.slider("Minimum Brightness", 0, 100, DEFAULT_MIN_BRIGHTNESS)
st.session_state.max_brightness = st.sidebar.slider("Maximum Brightness", 0, 100, DEFAULT_MAX_BRIGHTNESS)
st.session_state.smoothing_factor = st.sidebar.slider("Brightness Smoothing Factor", 0.01, 1.0, DEFAULT_SMOOTHING_FACTOR)
st.session_state.stress_threshold = st.sidebar.slider("Stress Notification Threshold", 0, 100, DEFAULT_STRESS_THRESHOLD)
st.session_state.notification_cooldown = st.sidebar.slider("Notification Cooldown (s)", 5, 60, DEFAULT_NOTIFICATION_COOLDOWN)

# Main Layout
st.title("🧠 Real-Time Stress Detection & Mitigation System")
col1, col2 = st.columns([2, 1.2])

with col1:
    st.header("Webcam Feed")
    webrtc_streamer(
        key="webcam",
        video_frame_callback=video_frame_callback,
        media_stream_constraints={"video": True, "audio": False},
        async_processing=True
    )

with col2:
    st.header("Live Analysis")
    
    # UI Placeholders
    emotion_metric = st.empty()
    status_alert = st.empty()
    
    st.markdown("---")
    st.subheader("Real-Time Data")
    stress_bar = st.empty()
    chart_display = st.empty()
    
    st.markdown("---")
    st.subheader("Session Analytics")
    col_a, col_b = st.columns(2)
    avg_metric = col_a.empty()
    peak_metric = col_b.empty()

# Update UI once per render
update_ui(emotion_metric, status_alert, stress_bar, chart_display, avg_metric, peak_metric)

# Auto-refresh every 100ms
time.sleep(0.1)
st.rerun()
