# 🚀 Neurolens - Pre-Flight Checklist

## Before Running - Quick Verification

### ✅ System Requirements
- [ ] Docker installed and running
- [ ] Docker Compose installed
- [ ] Python 3.11+ installed (for native backend)
- [ ] Webcam connected and working

### ✅ Project Files
- [ ] YOLO model weights exist at: `runs/detect/emotion_model_train/weights/best.pt`
- [ ] Backend files present in `/backend` folder
- [ ] Frontend files present in `/frontend` folder
- [ ] `docker-compose.yml` exists in root

### ✅ Port Availability
- [ ] Port 3000 is free (Frontend)
- [ ] Port 8001 is free (Backend)

**Check ports with:**
```bash
netstat -ano | findstr :3000
netstat -ano | findstr :8001
```
(No output = ports are free)

---

## 🎯 Choose Your Running Mode

### Option A: Native Hardware Control ⭐ RECOMMENDED
**Use this if you want:**
- ✅ Real screen brightness control
- ✅ Native OS notifications
- ✅ Full hardware integration

**Steps:**
1. Start frontend container:
   ```bash
   docker compose up -d frontend
   ```

2. Start native backend:
   ```bash
   run_native_backend.bat
   ```

3. Open browser: http://localhost:3000

---

### Option B: Fully Dockerized
**Use this if you want:**
- ✅ Quick demo/testing
- ✅ No hardware control needed
- ✅ Isolated environment

**Steps:**
1. Start all services:
   ```bash
   docker compose up -d
   ```

2. Open browser: http://localhost:3000

---

## 🔍 Verify Everything is Working

### 1. Check Backend Health
Open: http://localhost:8001/api/health

**Expected response:**
```json
{
  "status": "ok",
  "model_loaded": true
}
```

### 2. Check Frontend
Open: http://localhost:3000

**You should see:**
- ✅ Dashboard with webcam feed section
- ✅ Emotion display panel
- ✅ Stress gauge
- ✅ Real-time chart
- ✅ Start Monitoring button

### 3. Test Camera Access
1. Click "Start Monitoring"
2. Allow camera access when prompted
3. You should see your webcam feed
4. Emotion detection should start automatically

### 4. Test Settings
1. Navigate to Settings page
2. Adjust brightness range
3. Adjust stress threshold
4. Changes should save automatically

---

## 🐛 Quick Troubleshooting

### Backend won't start
```bash
# Check if port 8001 is in use
netstat -ano | findstr :8001

# If in use, kill the process or use different port
```

### Frontend won't start
```bash
# Check if port 3000 is in use
netstat -ano | findstr :3000

# Check Docker logs
docker compose logs frontend
```

### Camera not working
- Grant browser camera permissions
- Close other apps using camera
- Try different browser
- Check browser console for errors (F12)

### Model not loading
- Verify file exists: `runs/detect/emotion_model_train/weights/best.pt`
- Check Docker volume mount in docker-compose.yml
- Check backend logs: `docker compose logs backend`

---

## 📊 Expected Behavior

### When Monitoring is Active:
1. ✅ Webcam feed shows in real-time
2. ✅ Emotion updates every ~1 second
3. ✅ Stress level updates smoothly (5-second average)
4. ✅ Chart updates continuously
5. ✅ Brightness adjusts automatically (native mode only)
6. ✅ Notifications appear when stress > threshold

### Performance Metrics:
- **Frame Rate:** ~6 FPS (optimal for accuracy)
- **Emotion Update:** Every 1 second (6 frames)
- **Stress Update:** Every 5 seconds (30 frames rolling average)
- **Chart Update:** Real-time
- **Brightness Update:** Smooth transitions

---

## ✅ All Systems Go!

If all checks pass, you're ready to use Neurolens!

**First Time Setup:**
1. Start the application (Option A or B)
2. Allow camera permissions
3. Allow notification permissions
4. Configure settings to your preference
5. Click "Start Monitoring"
6. Relax and let Neurolens monitor your stress!

---

## 📞 Need Help?

Check the full status report: `PROJECT_STATUS_REPORT.md`

**Common Issues:**
- Port conflicts → Kill processes or change ports
- Camera access → Check browser permissions
- Model not found → Verify file path
- Docker issues → Restart Docker Desktop

---

**Happy Monitoring! 🧠✨**
