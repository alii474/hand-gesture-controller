# Hand Gesture Controller

Control your PC with hand gestures using MediaPipe and OpenCV.

## Features

- ☝️ **Volume Up** - Index finger up
- 👆 **Volume Down** - Index + Middle fingers up  
- ✋ **Scroll Up** - Open hand (all 5 fingers)
- 🤚 **Scroll Down** - Closed fist (0 fingers)
- 👌 **Pause/Resume** - OK sign (thumb + index touching)

## Installation

```bash
# Create virtual environment (recommended)
py -3.13 -m venv .venv
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

> **Note:** The hand detection model (`hand_landmarker.task`) is automatically downloaded on first run (~8 MB).

## Usage

```bash
python gesture_controller.py
```

**Controls:**
- Show your hand to camera
- Use gestures to control volume and scroll
- Press **'q'** to quit

## Requirements

- Python 3.10 - 3.13 (**Python 3.14 not supported** — MediaPipe compatibility issue)
- Webcam
- Windows (for volume control)

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Camera not found | Check webcam connection |
| Gestures not detected | Ensure good lighting, keep hand 1-2 ft from camera |
| Volume not changing | Run as Administrator |
| Slow performance | Close other applications |
| `function 'free' not found` error | Use Python 3.13 or lower (not 3.14) |

## Tips

- Use good lighting
- Keep hand clearly visible
- Make distinct gestures
- Small pause between gestures for better recognition
