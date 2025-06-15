# Scene Capture Tool (Mac)

This tool captures scene-change screenshots from the first 4 seconds of a video (e.g. Facebook Ad).

## 🔧 Setup (One-Time)
1. Open Terminal
2. Install Python packages:

   pip3 install opencv-python moviepy numpy

## ▶️ How to Use
1. Place your video file in this folder and name it: ad.mp4
2. Run the script:

   python3 scene_capture.py

3. Your scene screenshots will appear in the `screenshots` folder.

## 🎛️ Adjustments
- Change `threshold` in `scene_capture.py` to adjust scene-change sensitivity.
- It processes every 2nd frame to improve speed.

Enjoy!
