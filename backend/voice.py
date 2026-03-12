from transformers import pipeline
import os

# Lazy load to avoid startup delay
emotion_classifier = None

def detect_voice_emotion(audio_path: str):
    global emotion_classifier
    
    if emotion_classifier is None:
        emotion_classifier = pipeline(
            "audio-classification",
            model="ehcalabres/wav2vec2-lg-xlsr-en-speech-emotion-recognition"
        )
    
    result = emotion_classifier(audio_path)
    emotion = result[0]["label"].capitalize()
    confidence = float(result[0]["score"])
    
    # Cleanup temp file
    try:
        if os.path.exists(audio_path) and "temp_audio" in audio_path:
            os.remove(audio_path)
    except:
        pass
    
    return emotion, confidence