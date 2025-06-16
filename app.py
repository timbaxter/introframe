import streamlit as st
import cv2
import numpy as np
from moviepy.editor import VideoFileClip
import os
import tempfile # For handling temporary files

# --- Streamlit App Interface ---
st.set_page_config(page_title="Ad Scene Capture Tool", layout="wide")

st.title("📸 Facebook Ad Scene Capture")
st.markdown("Upload your MP4 ad, and Introframe will extract the key scene changes from the first 4 seconds!" \
"" \
"Leave the sunsitivty on 3,000,000,000. Adjust the seconds to the average video length played")

# --- File Uploader ---
uploaded_file = st.file_uploader("Choose an MP4 video file", type=["mp4"])

# --- Sensitivity Slider (Threshold) ---
# Use min/max/default that are reasonable for the new total_pixel_difference method
threshold = st.slider(
    "Adjust Sensitivity (Higher = Less Sensitive)",
    min_value=100000,   # Lower bound for sum of pixel differences
    max_value=10000000, # Upper bound
    value=3000000,      # Default from our last successful test
    step=100000,        # Step size for adjustment
    help="Increase this value if you're getting too many images for minor changes. Decrease if you're missing scene changes."
)

# --- NEW: Screenshot Duration Slider ---
max_duration_sec = st.slider(
    "Screenshot Duration (seconds)",
    min_value=3,
    max_value=9,
    value=4, # Default value, currently 4 seconds
    step=1,
    help="Adjust the length of the video to analyze for scene changes (3 to 9 seconds)."
)

if uploaded_file is not None:
    # Use columns to control the video's display width
    # The [0.5, 0.5] means two columns of equal width.
    # You can adjust the ratio, e.g., [0.4, 0.6] to make the video column 40% width.
    video_col, _ = st.columns([0.5, 0.5]) # Video takes 60% of width, second col takes 40%

    with video_col:
        st.video(uploaded_file, format="video/mp4", start_time=0)
    
    # You can add content to the second column if you like, e.g.:
    # with _: # This is the second column
    #     st.markdown("### Video Preview")
    #     st.info("The extracted scene screenshots will appear below after processing.")

    if st.button("Extract Scene Screenshots"):
        # --- Create temporary directories ---
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_video_path = os.path.join(temp_dir, uploaded_file.name)
            temp_trimmed_video_path = os.path.join(temp_dir, "trimmed_video.mp4")
            output_screenshots_dir = os.path.join(temp_dir, "screenshots_output")
            os.makedirs(output_screenshots_dir, exist_ok=True) # Ensure output dir exists

            # Save uploaded file to a temporary location
            with open(temp_video_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            st.success(f"Video saved temporarily to: {temp_video_path}")

            try:
                # --- Trim Video to First {max_duration_sec} Seconds ---
                st.info("Trimming video to the first 4 seconds...")
                clip = VideoFileClip(temp_video_path).subclip(0, max_duration_sec)
                clip.write_videofile(temp_trimmed_video_path, codec='libx264', audio=False, preset='veryfast', logger=None)
                st.success("Video trimmed successfully.")

                # --- Process Video for Frame Changes ---
                st.info("Analyzing video for scene changes...")
                cap = cv2.VideoCapture(temp_trimmed_video_path)
                success, prev_frame = cap.read()
                frame_count = 0
                saved_count = 0
                
                # Placeholder for displaying progress
                progress_bar = st.progress(0)
                status_text = st.empty()

                if not success:
                    st.error("Could not read the video file. Please check its format.")
                    cap.release()
                    st.stop()

                while success:
                    success, frame = cap.read()
                    if not success:
                        break
                    
                    frame_count += 1
                    
                    # Update progress bar every 10 frames
                    if frame_count % 10 == 0:
                        progress_value = min(1.0, frame_count / (clip.fps * max_duration_sec)) #allowing for max duration
                        progress_bar.progress(progress_value)
                        status_text.text(f"Processing frame {frame_count}...")

                    if frame_count % 2 != 0:  # Check every 2nd frame
                        continue

                    # Convert to grayscale for comparison
                    gray_prev = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
                    gray_curr = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

                    # Calculate pixel-wise difference (sum of absolute differences)
                    diff = cv2.absdiff(gray_prev, gray_curr)
                    total_pixel_difference = np.sum(diff)

                    # Save if there's a big change
                    if total_pixel_difference > threshold:
                        filename = f"{output_screenshots_dir}/scene_{saved_count:03}.jpg"
                        cv2.imwrite(filename, frame)
                        saved_count += 1
                        prev_frame = frame # Update prev_frame to the last saved frame

                    prev_frame = frame # Always update prev_frame for continuous comparison

                cap.release()
                progress_bar.progress(1.0)
                status_text.text("Analysis complete!")

                st.success(f"✅ Done! Saved {saved_count} scene-change screenshots.")

                # --- Display Results ---
                if saved_count > 0:
                    st.subheader("Extracted Scenes:")
                    cols = st.columns(4) # Display images in 4 columns
                    image_files = sorted([f for f in os.listdir(output_screenshots_dir) if f.endswith('.jpg')])
                    
                    for i, img_file in enumerate(image_files):
                        with open(os.path.join(output_screenshots_dir, img_file), "rb") as f:
                            img_bytes = f.read()
                        cols[i % 4].image(img_bytes, caption=f"Scene {i+1}", use_container_width=True)
                else:
                    st.info("No significant scene changes detected with the current sensitivity.")

            except Exception as e:
                st.error(f"An error occurred during video processing: {e}")

            # Temporary directory will be automatically cleaned up on exit of 'with' block