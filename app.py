import streamlit as st
import cv2
import numpy as np
import os
import tempfile

# --- Streamlit App Interface (General Config) ---
st.set_page_config(page_title="Ad Scene Capture Tool", layout="wide", page_icon="📸")

# --- Main Application Title & Description ---
st.title("📸 Intro Frame")
st.markdown("Upload your MP4 ad(s), and I'll extract key scene changes from the first few seconds!")

# --- File Uploader ---
uploaded_files = st.file_uploader("Choose MP4 video files", type=["mp4"], accept_multiple_files=True)

# --- Sensitivity Slider (Threshold) ---
# Note: this is now the AVERAGE per-pixel brightness difference (0-255 scale),
# not the summed difference across the whole frame. The old version summed every
# pixel's difference, which scales with resolution and made the slider's range
# meaningless for typical HD video (nearly every frame cleared even the max value).
threshold = st.slider(
    "Adjust Sensitivity (Higher = Less Sensitive)",
    min_value=1.0,
    max_value=50.0,
    value=8.0,
    step=0.5,
    help="This is the average brightness change per pixel between frames (0-255 scale). Increase this value if you're getting too many images for minor changes. Decrease if you're missing scene changes."
)

# --- Screenshot Duration Slider ---
max_duration_sec = st.slider(
    "Screenshot Duration (seconds)",
    min_value=3,
    max_value=9,
    value=4,
    step=1,
    help="Adjust the length of the video to analyze for scene changes (3 to 9 seconds)."
)

# --- Display Previews for Uploaded Files ---
if uploaded_files:
    st.markdown("---")
    st.subheader("Uploaded Video Previews:")

    cols_per_row = 2
    columns = st.columns(cols_per_row)

    for i, uploaded_file in enumerate(uploaded_files):
        with columns[i % cols_per_row]:
            st.text(f"{uploaded_file.name}")
            st.video(uploaded_file, format="video/mp4", start_time=0, width=400)

    st.markdown("---")

    # --- Process Button ---
    if st.button("Extract Scene Screenshots from All Uploaded Videos"):
        st.subheader("Processing Results:")

        for i, uploaded_file in enumerate(uploaded_files):
            st.markdown(f"### Processing: **{uploaded_file.name}**")

            with tempfile.TemporaryDirectory() as temp_dir:
                temp_video_path = os.path.join(temp_dir, uploaded_file.name)
                output_screenshots_dir = os.path.join(temp_dir, f"screenshots_output_{i}")
                os.makedirs(output_screenshots_dir, exist_ok=True)

                with open(temp_video_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())

                try:
                    cap = cv2.VideoCapture(temp_video_path)
                    if not cap.isOpened():
                        st.error(f"Could not open video file '{uploaded_file.name}'. Please check its format or if it's corrupted.")
                        st.markdown("---")
                        continue

                    fps = cap.get(cv2.CAP_PROP_FPS)
                    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                    duration_video = total_frames / fps

                    frames_to_process = int(fps * max_duration_sec)
                    if frames_to_process > total_frames:
                        frames_to_process = total_frames

                    success, prev_frame = cap.read()
                    frame_count = 0
                    saved_count = 0

                    progress_bar = st.progress(0)
                    status_text = st.empty()

                    while success and frame_count < frames_to_process:
                        success, frame = cap.read()
                        if not success:
                            break

                        frame_count += 1

                        progress_value = min(1.0, frame_count / frames_to_process)
                        progress_bar.progress(progress_value)
                        status_text.text(f"Processing frame {frame_count} of {frames_to_process} for '{uploaded_file.name}'...")

                        if frame_count == 1:
                            prev_frame = frame
                            continue

                        gray_prev = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
                        gray_curr = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

                        diff = cv2.absdiff(gray_prev, gray_curr)
                        avg_pixel_difference = np.mean(diff)

                        if avg_pixel_difference > threshold:
                            filename = f"{output_screenshots_dir}/scene_{saved_count:03}.jpg"
                            cv2.imwrite(filename, frame)
                            saved_count += 1
                            prev_frame = frame
                        else:
                            prev_frame = frame

                    cap.release()
                    progress_bar.progress(1.0)
                    status_text.text(f"Analysis complete for '{uploaded_file.name}'!")

                    st.success(f"✅ Done! Saved {saved_count} scene-change screenshots for '{uploaded_file.name}'.")

                    if saved_count > 0:
                        st.markdown("#### Extracted Scenes:")
                        cols = st.columns(4)
                        image_files = sorted([f for f in os.listdir(output_screenshots_dir) if f.endswith('.jpg')])

                        for img_idx, img_file in enumerate(image_files):
                            with open(os.path.join(output_screenshots_dir, img_file), "rb") as f:
                                img_bytes = f.read()
                            cols[img_idx % 4].image(img_bytes, caption=f"Scene {img_idx+1}", use_container_width=True)
                    else:
                        st.info(f"No significant scene changes detected for '{uploaded_file.name}' with the current sensitivity.")

                except Exception as e:
                    st.error(f"An error occurred during processing '{uploaded_file.name}': {e}")
                finally:
                    pass

            st.markdown("---")
