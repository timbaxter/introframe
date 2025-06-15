import cv2
import os
import numpy as np
from moviepy.editor import VideoFileClip

# === SETTINGS ===
video_path = "ad.mp4"  # Your downloaded video file
output_folder = "screenshots"
max_duration_sec = 4
threshold = 3500000  # Sensitivity of scene change (lower = more sensitive)

# === PREPARE FOLDER ===
if not os.path.exists(output_folder):
    os.makedirs(output_folder)

# === TRIM VIDEO TO FIRST 4 SECONDS ===
clip = VideoFileClip(video_path).subclip(0, max_duration_sec)
clip.write_videofile("trimmed_ad.mp4", codec='libx264', audio=False)

# === PROCESS VIDEO FOR FRAME CHANGES ===
cap = cv2.VideoCapture("trimmed_ad.mp4")
success, prev_frame = cap.read()
frame_count = 0
saved_count = 0

while success:
    success, frame = cap.read()
    if not success:
        break
    frame_count += 1
    if frame_count % 2 != 0:
        continue

    gray_prev = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
    gray_curr = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    diff = cv2.absdiff(gray_prev, gray_curr)
    total_pixel_difference = np.sum(diff)

    if total_pixel_difference > threshold:
        filename = f"{output_folder}/scene_{saved_count:03}.jpg"
        cv2.imwrite(filename, frame)
        saved_count += 1

    prev_frame = frame

cap.release()
print(f"✅ Done! Saved {saved_count} scene-change screenshots.")
