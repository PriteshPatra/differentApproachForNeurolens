"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { Mic, MicOff } from "lucide-react";

interface VoiceAnalyzerProps {
  isActive: boolean;
  onVoiceStressUpdate: (stress: number) => void;
}

const FFT_SIZE = 256;
const HISTORY_SIZE = 30; // ~5 seconds at ~6fps equivalent

export default function VoiceAnalyzer({ isActive, onVoiceStressUpdate }: VoiceAnalyzerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const animFrameRef = useRef<number>(0);
  const voiceHistoryRef = useRef<number[]>([]);

  const [volume, setVolume] = useState(0);
  const [pitch, setPitch] = useState(0);
  const pitchHistoryRef = useRef<number[]>([]);
  const [voiceStress, setVoiceStress] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const computeVoiceStress = useCallback((vol: number, pitchHz: number): number => {
    // Volume stress: loud speech (>70%) = high stress
    const volStress = Math.min(100, vol * 1.4);
    // Pitch stress: elevated pitch (>200Hz) correlates with stress
    const pitchStress = pitchHz > 80
      ? Math.min(100, ((pitchHz - 80) / 320) * 100)
      : 0;
    return Math.round(volStress * 0.6 + pitchStress * 0.4);
  }, []);

  const getAutocorrelationPitch = useCallback((buffer: Float32Array, sampleRate: number): number => {
    const SIZE = buffer.length;
    const MAX_SAMPLES = Math.floor(SIZE / 2);

    // RMS check — lower threshold so normal speech isn't cut
    let rms = 0;
    for (let i = 0; i < SIZE; i++) rms += buffer[i] * buffer[i];
    rms = Math.sqrt(rms / SIZE);
    if (rms < 0.003) return -1; // true silence, signal caller to keep last value

    // Build normalized autocorrelation array
    const corr = new Float32Array(MAX_SAMPLES);
    for (let offset = 0; offset < MAX_SAMPLES; offset++) {
      let sum = 0;
      for (let i = 0; i < MAX_SAMPLES; i++) sum += buffer[i] * buffer[i + offset];
      corr[offset] = sum;
    }
    // Normalize by zero-lag so values are in [-1, 1]
    const zeroLag = corr[0] || 1;
    for (let i = 0; i < MAX_SAMPLES; i++) corr[i] /= zeroLag;

    // Skip the initial peak at offset=0: find first valley (where corr starts rising again)
    let valleyIdx = 1;
    while (valleyIdx < MAX_SAMPLES - 1 && corr[valleyIdx] > corr[valleyIdx + 1]) valleyIdx++;

    // Find the best peak after the valley — this is the fundamental period
    let bestOffset = -1;
    let bestVal = 0.3; // minimum correlation threshold to count as a real pitch
    for (let i = valleyIdx; i < MAX_SAMPLES; i++) {
      if (corr[i] > bestVal) {
        bestVal = corr[i];
        bestOffset = i;
      }
    }

    if (bestOffset < 1) return -1; // no clear pitch found
    return sampleRate / bestOffset;
  }, []);

  const drawWaveform = useCallback(() => {
    const analyser = analyserRef.current;
    const canvas = canvasRef.current;
    if (!analyser || !canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);
    const timeData = new Float32Array(analyser.fftSize);

    analyser.getByteFrequencyData(dataArray);
    analyser.getFloatTimeDomainData(timeData);

    // Volume (RMS)
    let rms = 0;
    for (let i = 0; i < timeData.length; i++) rms += timeData[i] * timeData[i];
    const rmsVol = Math.min(100, Math.sqrt(rms / timeData.length) * 300);
    setVolume(Math.round(rmsVol));

    // Pitch — smooth over last 8 valid readings to avoid jitter
    const rawPitch = getAutocorrelationPitch(timeData, audioCtxRef.current!.sampleRate);
    if (rawPitch > 0) {
      // Only accept human voice range: 60Hz–400Hz
      const clamped = Math.min(400, Math.max(60, rawPitch));
      pitchHistoryRef.current.push(clamped);
      if (pitchHistoryRef.current.length > 8) pitchHistoryRef.current.shift();
    }
    const smoothedPitch = pitchHistoryRef.current.length > 0
      ? Math.round(pitchHistoryRef.current.reduce((a, b) => a + b, 0) / pitchHistoryRef.current.length)
      : 0;
    setPitch(smoothedPitch);
    const clampedPitch = smoothedPitch;

    // Voice stress
    const vs = computeVoiceStress(rmsVol, clampedPitch);
    voiceHistoryRef.current.push(vs);
    if (voiceHistoryRef.current.length > HISTORY_SIZE) voiceHistoryRef.current.shift();
    const smoothed = Math.round(
      voiceHistoryRef.current.reduce((a, b) => a + b, 0) / voiceHistoryRef.current.length
    );
    setVoiceStress(smoothed);
    onVoiceStressUpdate(smoothed);

    // Draw waveform
    const { width, height } = canvas;
    ctx.clearRect(0, 0, width, height);

    const gradient = ctx.createLinearGradient(0, 0, width, 0);
    gradient.addColorStop(0, "#8b5cf6");
    gradient.addColorStop(0.5, "#0ea5e9");
    gradient.addColorStop(1, "#8b5cf6");

    ctx.lineWidth = 2;
    ctx.strokeStyle = gradient;
    ctx.beginPath();

    const sliceWidth = width / bufferLength;
    let x = 0;
    for (let i = 0; i < bufferLength; i++) {
      const v = dataArray[i] / 128.0;
      const y = (v * height) / 2;
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      x += sliceWidth;
    }
    ctx.lineTo(width, height / 2);
    ctx.stroke();

    // Glow effect when loud
    if (rmsVol > 30) {
      ctx.shadowBlur = 10;
      ctx.shadowColor = "#8b5cf6";
      ctx.stroke();
      ctx.shadowBlur = 0;
    }

    animFrameRef.current = requestAnimationFrame(drawWaveform);
  }, [computeVoiceStress, getAutocorrelationPitch, onVoiceStressUpdate]);

  useEffect(() => {
    if (!isActive) {
      cancelAnimationFrame(animFrameRef.current);
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      audioCtxRef.current?.close();
      audioCtxRef.current = null;
      analyserRef.current = null;
      voiceHistoryRef.current = [];
      pitchHistoryRef.current = [];
      setVolume(0);
      setPitch(0);
      setVoiceStress(0);
      onVoiceStressUpdate(0);

      // Clear canvas
      const canvas = canvasRef.current;
      if (canvas) {
        const ctx = canvas.getContext("2d");
        ctx?.clearRect(0, 0, canvas.width, canvas.height);
      }
      return;
    }

    (async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
        streamRef.current = stream;

        const audioCtx = new AudioContext();
        audioCtxRef.current = audioCtx;

        const analyser = audioCtx.createAnalyser();
        analyser.fftSize = FFT_SIZE;
        analyserRef.current = analyser;

        const source = audioCtx.createMediaStreamSource(stream);
        source.connect(analyser);

        setError(null);
        drawWaveform();
      } catch {
        setError("Microphone access denied.");
      }
    })();

    return () => {
      cancelAnimationFrame(animFrameRef.current);
    };
  }, [isActive, drawWaveform, onVoiceStressUpdate]);

  const stressColor =
    voiceStress >= 75 ? "var(--color-danger)"
    : voiceStress >= 40 ? "var(--color-warning)"
    : "var(--color-success)";

  return (
    <div className="glass-panel" style={{ borderLeft: "4px solid #8b5cf6" }}>
      <div className="glass-header" style={{ marginBottom: "1rem", paddingBottom: "0.75rem" }}>
        <h2 style={{ margin: 0, fontSize: "1.2rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
          {isActive && !error ? (
            <Mic size={20} style={{ color: "#8b5cf6" }} />
          ) : (
            <MicOff size={20} style={{ color: "var(--text-muted)" }} />
          )}
          Voice Analysis
        </h2>
        {isActive && !error && (
          <span className="badge" style={{ background: "rgba(139,92,246,0.1)", color: "#8b5cf6" }}>
            <span className="animate-pulse" style={{ width: 8, height: 8, borderRadius: "50%", background: "currentColor", display: "inline-block" }} />
            Listening
          </span>
        )}
      </div>

      {/* Waveform Canvas */}
      <div style={{ background: "rgba(0,0,0,0.3)", borderRadius: 8, overflow: "hidden", marginBottom: "1rem", height: 64, display: "flex", alignItems: "center", justifyContent: "center" }}>
        {error ? (
          <p style={{ color: "var(--color-danger)", fontSize: "0.85rem" }}>{error}</p>
        ) : !isActive ? (
          <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Start monitoring to enable voice analysis</p>
        ) : (
          <canvas ref={canvasRef} width={500} height={64} style={{ width: "100%", height: "100%" }} />
        )}
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-3" style={{ gap: "0.75rem", marginBottom: "1rem" }}>
        <div style={{ textAlign: "center" }}>
          <p style={{ color: "var(--text-muted)", fontSize: "0.75rem", marginBottom: "0.25rem" }}>Volume</p>
          <p style={{ fontSize: "1.25rem", fontWeight: 600, color: "var(--accent-secondary)" }}>{volume}%</p>
        </div>
        <div style={{ textAlign: "center" }}>
          <p style={{ color: "var(--text-muted)", fontSize: "0.75rem", marginBottom: "0.25rem" }}>Pitch</p>
          <p style={{ fontSize: "1.25rem", fontWeight: 600, color: "var(--accent-primary)" }}>{pitch} Hz</p>
        </div>
        <div style={{ textAlign: "center" }}>
          <p style={{ color: "var(--text-muted)", fontSize: "0.75rem", marginBottom: "0.25rem" }}>Voice Stress</p>
          <p style={{ fontSize: "1.25rem", fontWeight: 600, color: stressColor }}>{voiceStress}%</p>
        </div>
      </div>

      {/* Voice Stress Bar */}
      <div className="progress-container">
        <div className="progress-bar" style={{ width: `${voiceStress}%`, background: stressColor, transition: "width 0.4s ease, background 0.4s ease" }} />
      </div>
    </div>
  );
}
