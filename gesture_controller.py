"""
Hand Gesture Controller for PC
Control volume and scroll with hand gestures using MediaPipe + OpenCV

Gestures:
- ☝️ Index finger up: Volume Up
- 👆 Index + Middle up: Volume Down  
- ✋ Open hand: Scroll Up
- 🤚 Closed fist: Scroll Down
- 👌 OK sign: Pause/Resume
"""

import cv2
import numpy as np
import time
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
import win32api
import win32con

# MediaPipe imports for 0.10.x
try:
    from mediapipe.tasks.python.vision.hand_landmarker import HandLandmarker, HandLandmarkerOptions
    from mediapipe.tasks.python.vision.core.vision_task_running_mode import VisionTaskRunningMode as RunningMode
    from mediapipe.tasks.python.core.base_options import BaseOptions
    import mediapipe as mp
    MEDIAPIPE_AVAILABLE = True
    print("[INFO] Using MediaPipe Tasks API (0.10.x)")
except ImportError as e:
    print(f"[ERROR] MediaPipe import failed: {e}")
    MEDIAPIPE_AVAILABLE = False


class HandGestureController:
    def __init__(self):
        if not MEDIAPIPE_AVAILABLE:
            raise RuntimeError("MediaPipe not available. Run: pip install mediapipe")

        # Model will be loaded during run() to speed up window appearance
        self.model_path = self._get_model_path()
        self.options = HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=self.model_path),
            num_hands=1,
            min_hand_detection_confidence=0.5,
            min_hand_presence_confidence=0.5,
            min_tracking_confidence=0.5,
            running_mode=RunningMode.VIDEO
        )
        self.landmarker = None
        self.frame_count = 0
        self.process_every_n_frames = 2  # Process every 2nd frame to reduce CPU load

        # Volume control setup (pycaw 2025+ API)
        device = AudioUtilities.GetSpeakers()
        self.volume = device.EndpointVolume
        
        self.vol_range = self.volume.GetVolumeRange()
        self.min_vol, self.max_vol = self.vol_range[0], self.vol_range[1]

        # State variables
        self.paused = False
        self.last_gesture = None
        self.gesture_cooldown = 0.1  # seconds (faster response)
        self.last_gesture_time = 0
        self.gesture_history = []  # For stability check
        self.stability_frames = 2  # Require 2 consecutive same gestures (faster response)

        print("[INFO] Hand Gesture Controller initialized")
        print("[INFO] Controls:")
        print("  ☝️ Index UP: Volume UP")
        print("  👆 2 Fingers UP: Volume DOWN")
        print("  ✋ Open Hand: Scroll UP")
        print("  🤚 Fist: Scroll DOWN")
        print("  👌 OK Sign: PAUSE/RESUME")
        print("  Press 'q' to quit\n")

    def _get_model_path(self):
        """Get or download hand landmarker model."""
        import os
        import urllib.request
        import ssl
        
        model_file = "hand_landmarker.task"
        model_url = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
        
        if os.path.exists(model_file):
            return model_file
        
        print("[INFO] Downloading MediaPipe hand landmarker model...")
        print("[INFO] This is a one-time download (~8 MB)")
        
        try:
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
            
            req = urllib.request.Request(model_url, headers={'User-Agent': 'Mozilla/5.0'})
            
            with urllib.request.urlopen(req, context=ssl_ctx, timeout=60) as response:
                total_size = int(response.headers.get('Content-Length', 0))
                downloaded = 0
                chunk_size = 8192
                
                with open(model_file, 'wb') as f:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        if total_size > 0:
                            percent = (downloaded / total_size) * 100
                            print(f"\r[INFO] Progress: {percent:.1f}%")
            
            print(f"\n[SUCCESS] Model downloaded: {model_file}")
            return model_file
            
        except Exception as e:
            print(f"\n[ERROR] Download failed: {e}")
            raise RuntimeError("Failed to download hand landmarker model")

    def detect_fingers_up(self, landmarks):
        """Detect which fingers are up with better precision."""
        fingers = []

        # Thumb (check distance from palm center to be hand-agnostic)
        # We compare thumb tip (4) distance to pinky mcp (17) vs thumb cmc (2)
        if landmarks[4].x < landmarks[3].x: # Basic check for right hand
             fingers.append(1)
        else:
             fingers.append(0)

        # Other 4 fingers (Strict check: tip must be significantly above pip)
        finger_tips = [8, 12, 16, 20]  # Index, Middle, Ring, Pinky
        finger_pips = [6, 10, 14, 18]

        for tip, pip in zip(finger_tips, finger_pips):
            if landmarks[tip].y < landmarks[pip].y - 0.02: # Added offset for stability
                fingers.append(1)
            else:
                fingers.append(0)

        return fingers

    def get_gesture(self, fingers, landmarks):
        """Determine gesture strictly based on user requirements."""
        total_fingers = sum(fingers)
        
        # ✋ Open Hand (Scroll Up)
        if total_fingers >= 4:
            return "SCROLL_UP"
            
        # ✊ Fist (Scroll Down)
        if total_fingers == 0:
            return "SCROLL_DOWN"
            
        # ☝️ Index Finger ONLY (Volume Up)
        if fingers[1] == 1 and fingers[2] == 0 and fingers[3] == 0:
            return "VOL_UP"
            
        # 👆 Index + Middle (Volume Down)
        if fingers[1] == 1 and fingers[2] == 1 and fingers[3] == 0:
            return "VOL_DOWN"

        return "NONE"

    def execute_action(self, gesture):
        """Execute action based on gesture."""
        current_time = time.time()

        # Check cooldown only (allow repeated gestures)
        if current_time - self.last_gesture_time < self.gesture_cooldown:
            return

        print(f"[DEBUG] Gesture detected: {gesture}")

        if gesture == "OK":
            self.paused = not self.paused
            self.last_gesture_time = current_time
            self.last_gesture = gesture
            print(f"[DEBUG] Action: {'PAUSED' if self.paused else 'RESUMED'}")
            return "PAUSED" if self.paused else "RESUMED"

        if self.paused:
            return "PAUSED"

        if gesture == "INDEX_UP":
            # Volume up
            current_vol = self.volume.GetMasterVolumeLevel()
            new_vol = min(current_vol + 2, self.max_vol)
            self.volume.SetMasterVolumeLevel(new_vol, None)
            self.last_gesture_time = current_time
            self.last_gesture = gesture
            print(f"[DEBUG] Action: VOLUME UP (from {current_vol:.1f} to {new_vol:.1f})")
            return "VOLUME UP"

        elif gesture == "TWO_FINGERS":
            # Volume down
            current_vol = self.volume.GetMasterVolumeLevel()
            new_vol = max(current_vol - 2, self.min_vol)
            self.volume.SetMasterVolumeLevel(new_vol, None)
            self.last_gesture_time = current_time
            self.last_gesture = gesture
            print(f"[DEBUG] Action: VOLUME DOWN (from {current_vol:.1f} to {new_vol:.1f})")
            return "VOLUME DOWN"

        elif gesture == "OPEN_HAND":
            # Scroll up
            win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, 0, 0, 120, 0)
            self.last_gesture_time = current_time
            self.last_gesture = gesture
            print(f"[DEBUG] Action: SCROLL UP")
            return "SCROLL UP"

        elif gesture == "FIST":
            # Scroll down
            win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, 0, 0, -120, 0)
            self.last_gesture_time = current_time
            self.last_gesture = gesture
            print(f"[DEBUG] Action: SCROLL DOWN")
            return "SCROLL DOWN"

        self.last_gesture = gesture
        print(f"[DEBUG] Action: NONE (unknown gesture)")
        return None

    def process_frame(self, frame):
        """Process a single frame."""
        # Flip frame horizontally for mirror effect
        frame = cv2.flip(frame, 1)
        h, w, _ = frame.shape
        self.frame_count += 1

        # Skip frames to reduce CPU load
        if self.frame_count % self.process_every_n_frames != 0:
            # Just show basic info without processing
            gesture_text = "PROCESSING..."
            action_text = ""
            color = (128, 128, 128)
            
            # Display status
            status = "PAUSED" if self.paused else "ACTIVE"
            status_color = (0, 0, 255) if self.paused else (0, 255, 0)
            
            cv2.putText(frame, f"Status: {status}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2)
            cv2.putText(frame, f"Gesture: {gesture_text}", (10, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
            cv2.putText(frame, "Q:Quit | OK Sign:Pause", (10, h - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
            return frame

        # Convert BGR to RGB
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Create MediaPipe Image object
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        
        # Detect hands (only if landmarker is ready)
        results = None
        if self.landmarker:
            results = self.landmarker.detect_for_video(mp_image, self.frame_count)
        else:
            gesture_text = "LOADING AI..."
            color = (0, 165, 255) # Orange

        gesture_text = "No Hand"
        action_text = ""
        color = (128, 128, 128)

        if results and results.hand_landmarks:
            for hand_landmarks in results.hand_landmarks:
                # Draw hand landmarks
                self._draw_landmarks(frame, hand_landmarks, w, h)

                # Detect fingers
                fingers = self.detect_fingers_up(hand_landmarks)

                # Get gesture
                gesture = self.get_gesture(fingers, hand_landmarks)

                # Stability check - add to history
                self.gesture_history.append(gesture)
                if len(self.gesture_history) > self.stability_frames:
                    self.gesture_history.pop(0)

                # Check if gesture is stable (same for all frames in history)
                stable_gesture = None
                if len(self.gesture_history) == self.stability_frames:
                    if all(g == self.gesture_history[0] for g in self.gesture_history):
                        stable_gesture = gesture

                # Map gesture to display text
                gesture_map = {
                    "VOL_UP": ("☝️ VOLUME UP", (0, 255, 0)),
                    "VOL_DOWN": ("👆 VOLUME DOWN", (0, 255, 255)),
                    "SCROLL_UP": ("✋ SCROLL UP", (255, 255, 0)),
                    "SCROLL_DOWN": ("✊ SCROLL DOWN", (0, 0, 255)),
                }

                gesture_text, color = gesture_map.get(gesture, ("WAITING...", (128, 128, 128)))

                # Execute actions based on stable gesture
                if gesture == "SCROLL_UP":
                    win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, 0, 0, 150, 0) # Faster scroll
                    action_text = "SCROLLING UP"
                elif gesture == "SCROLL_DOWN":
                    win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, 0, 0, -150, 0)
                    action_text = "SCROLLING DOWN"
                elif gesture == "VOL_UP":
                    current_vol = self.volume.GetMasterVolumeLevel()
                    new_vol = min(current_vol + 1.0, self.max_vol)
                    self.volume.SetMasterVolumeLevel(new_vol, None)
                    action_text = "VOLUME +"
                elif gesture == "VOL_DOWN":
                    current_vol = self.volume.GetMasterVolumeLevel()
                    new_vol = max(current_vol - 1.0, self.min_vol)
                    self.volume.SetMasterVolumeLevel(new_vol, None)
                    action_text = "VOLUME -"

                # Draw finger count
                finger_count = sum(fingers)
                cv2.putText(frame, f"Fingers: {finger_count}", (10, 120),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        # Display status
        status = "PAUSED" if self.paused else "ACTIVE"
        status_color = (0, 0, 255) if self.paused else (0, 255, 0)

        cv2.putText(frame, f"Status: {status}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2)
        cv2.putText(frame, f"Gesture: {gesture_text}", (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

        if action_text:
            cv2.putText(frame, f"Action: {action_text}", (10, 90),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        # Show controls hint
        cv2.putText(frame, "Q:Quit | OK Sign:Pause", (10, h - 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

        return frame

    def _draw_landmarks(self, frame, landmarks, w, h):
        """Draw hand landmarks on frame."""
        # Connections between landmarks (MediaPipe hand connections)
        connections = [
            (0, 1), (1, 2), (2, 3), (3, 4),  # Thumb
            (0, 5), (5, 6), (6, 7), (7, 8),  # Index
            (0, 9), (9, 10), (10, 11), (11, 12),  # Middle
            (0, 13), (13, 14), (14, 15), (15, 16),  # Ring
            (0, 17), (17, 18), (18, 19), (19, 20),  # Pinky
            (5, 9), (9, 13), (13, 17), (0, 17)  # Palm
        ]
        
        # Draw connections
        for start_idx, end_idx in connections:
            if start_idx < len(landmarks) and end_idx < len(landmarks):
                start_point = (int(landmarks[start_idx].x * w), int(landmarks[start_idx].y * h))
                end_point = (int(landmarks[end_idx].x * w), int(landmarks[end_idx].y * h))
                cv2.line(frame, start_point, end_point, (0, 255, 0), 2)
        
        # Draw landmarks
        for landmark in landmarks:
            x = int(landmark.x * w)
            y = int(landmark.y * h)
            cv2.circle(frame, (x, y), 4, (0, 0, 255), -1)

    def run(self):
        """Main loop with optimized startup."""
        print("[INFO] Initializing camera... please wait.")
        
        # Use CAP_DSHOW for faster startup on Windows
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        
        # Speed optimizations
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
        cap.set(cv2.CAP_PROP_FPS, 15)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not cap.isOpened():
            print("[ERROR] Cannot open camera!")
            return

        print("[INFO] Camera started. Loading AI model...")
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            # Show "Loading" on the first few frames while model initializes
            if self.landmarker is None:
                # Load model in the first loop iteration
                try:
                    self.landmarker = HandLandmarker.create_from_options(self.options)
                    print("[INFO] AI Model loaded successfully!")
                except Exception as e:
                    print(f"[ERROR] Failed to load AI: {e}")
                    cv2.putText(frame, "AI LOAD ERROR", (50, 100), 
                                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

            processed_frame = self.process_frame(frame)
            cv2.imshow("Hand Gesture Controller", processed_frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        cap.release()
        cv2.destroyAllWindows()
        print("[INFO] Controller stopped.")


def main():
    """Entry point."""
    try:
        controller = HandGestureController()
        controller.run()
    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
