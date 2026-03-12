"use client";

import { useEffect, useRef, useState, useCallback } from 'react';
import { predictFrame, detectVoice } from '@/lib/api';
import { Camera, CameraOff } from 'lucide-react';

interface WebcamCaptureProps {
  onAnalyticsUpdate: (data: { emotion: string; stress: number; confidence: number }) => void;
  isActive: boolean;
}

export default function WebcamCapture({ onAnalyticsUpdate, isActive }: WebcamCaptureProps) {

  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const isProcessingRef = useRef(false);

  const faceStressRef = useRef<number>(0);
  const voiceStressRef = useRef<number>(0);
  const previousStressRef = useRef<number>(0);

  const lastFaceEmotionRef = useRef<string>("Neutral");

  const [stream, setStream] = useState<MediaStream | null>(null);
  const [error, setError] = useState<string | null>(null);

  // ─── CAMERA & MIC START ─────────────────────────────────────
  const startCamera = useCallback(async () => {
    try {

      const mediaStream = await navigator.mediaDevices.getUserMedia({
        video: { width: 640, height: 480 },
        audio: true
      });

      setStream(mediaStream);

      if (videoRef.current) {
        videoRef.current.srcObject = mediaStream;
      }

      setError(null);

    } catch (err) {
      console.error('Failed to start camera/mic:', err);
      setError('Please allow camera and microphone access to use this feature.');
    }
  }, []);

  const stopCamera = useCallback(() => {
    if (stream) {
      stream.getTracks().forEach((track) => track.stop());
      setStream(null);
    }
  }, [stream]);

  // ─── CAMERA LIFECYCLE ─────────────────────────────────
  useEffect(() => {

    if (isActive && !stream) {
      startCamera();
    }

    else if (!isActive && stream) {
      stopCamera();
    }

    return () => stopCamera();

  }, [isActive, stream, startCamera, stopCamera]);

  // ─── FRAME PROCESSING LOOP ────────────────────────────
  useEffect(() => {

    if (!isActive || !stream) return;

    const processFrame = async () => {

      if (!videoRef.current || !canvasRef.current || isProcessingRef.current) return;

      const video = videoRef.current;
      const canvas = canvasRef.current;

      if (video.readyState === video.HAVE_ENOUGH_DATA) {

        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;

        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

        const base64Image = canvas.toDataURL('image/jpeg', 0.8);

        isProcessingRef.current = true;

        try {

          const res = await predictFrame(base64Image, 0.25);

          if (res) {

            faceStressRef.current = res.stress_level;
            lastFaceEmotionRef.current = res.emotion;

            const fusedStress =
              (0.6 * faceStressRef.current) +
              (0.4 * voiceStressRef.current);

            const smoothedStress =
              (0.7 * previousStressRef.current) +
              (0.3 * fusedStress);

            const finalStress = Math.round(smoothedStress);

            previousStressRef.current = finalStress;

            onAnalyticsUpdate({
              emotion: lastFaceEmotionRef.current,
              stress: finalStress,
              confidence: res.confidence
            });

          }

        } catch (err) {

          console.error("Frame processing failed", err);

        } finally {

          isProcessingRef.current = false;

        }

      }

    };

    const processingInterval = setInterval(processFrame, 166);

    return () => clearInterval(processingInterval);

  }, [isActive, stream, onAnalyticsUpdate]);

  // ─── VOICE RECORDING LOOP ─────────────────────────────
  useEffect(() => {

    if (!isActive || !stream) return;

    const recordVoice = () => {

      try {

        const recorder = new MediaRecorder(stream);
        let chunks: Blob[] = [];

        recorder.ondataavailable = (e) => chunks.push(e.data);

        recorder.onstop = async () => {

          const blob = new Blob(chunks, { type: "audio/webm" });

          const reader = new FileReader();

          reader.readAsDataURL(blob);

          reader.onloadend = async () => {

            const base64Audio = reader.result as string;

            const res = await detectVoice(base64Audio);

            if (res) {

              voiceStressRef.current = res.stress_level;

              const fusedStress =
                (0.6 * faceStressRef.current) +
                (0.4 * voiceStressRef.current);

              const smoothedStress =
                (0.7 * previousStressRef.current) +
                (0.3 * fusedStress);

              const finalStress = Math.round(smoothedStress);

              previousStressRef.current = finalStress;

              onAnalyticsUpdate({
                emotion: lastFaceEmotionRef.current,
                stress: finalStress,
                confidence: 1
              });

              console.log("Voice emotion:", res.emotion, "Final stress:", finalStress);

            }

          };

        };

        recorder.start();

        setTimeout(() => {

          if (recorder.state !== "inactive") {
            recorder.stop();
          }

        }, 3000);

      } catch (err) {

        console.error("Voice recording failed", err);

      }

    };

    recordVoice();

    const voiceInterval = setInterval(recordVoice, 5000);

    return () => clearInterval(voiceInterval);

  }, [isActive, stream, onAnalyticsUpdate]);

  // ─── UI ───────────────────────────────────────────────
  return (

    <div className="glass-panel" style={{ padding: 0, overflow: 'hidden' }}>

      <div className="glass-header" style={{ margin: 0, padding: '1rem', borderBottom: '1px solid var(--panel-border)' }}>

        <h2 style={{ margin: 0, fontSize: '1.2rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Camera size={20} className="text-gradient" /> Webcam Feed
        </h2>

        {isActive ? (
          <span className="badge" style={{ background: 'rgba(34, 197, 94, 0.1)', color: 'var(--color-success)' }}>
            <span className="animate-pulse" style={{ width: 8, height: 8, borderRadius: '50%', background: 'currentColor', display: 'inline-block' }}></span>
            Active
          </span>
        ) : (
          <span className="badge" style={{ background: 'rgba(239, 68, 68, 0.1)', color: 'var(--color-danger)' }}>
            <CameraOff size={14} /> Paused
          </span>
        )}

      </div>

      <div style={{ position: 'relative', width: '100%', aspectRatio: '4/3', background: '#000', display: 'flex', justifyContent: 'center', alignItems: 'center' }}>

        <canvas ref={canvasRef} style={{ display: 'none' }} />

        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            display: (isActive && !error) ? 'block' : 'none'
          }}
        />

        {error && (
          <div style={{ color: 'var(--color-danger)', textAlign: 'center', position: 'absolute' }}>
            <CameraOff size={48} style={{ margin: '0 auto 1rem', opacity: 0.5 }} />
            <p>{error}</p>
          </div>
        )}

        {!isActive && !error && (
          <div style={{ color: 'var(--text-muted)', textAlign: 'center', position: 'absolute' }}>
            <CameraOff size={48} style={{ margin: '0 auto 1rem', opacity: 0.5 }} />
            <p>Camera is turned off.</p>
          </div>
        )}

      </div>

    </div>

  );

}