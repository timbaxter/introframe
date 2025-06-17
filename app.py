import streamlit as st
import cv2
import numpy as np
from moviepy.editor import VideoFileClip
import os
import tempfile

# --- Streamlit App Interface ---
st.set_page_config(page_title="Ad Scene Capture Tool", layout="wide", page_icon="📸") # Added page_icon

st.title("📸 Facebook Ad Scene Capture")
st.markdown("Upload your MP4 ad(s), and I'll extract key scene changes from the first few seconds!")

# --- File Uploader ---
# NEW: Allow multiple files to be uploaded
uploaded_files = st.file_uploader("Choose MP4 video files", type=["mp4"], accept_multiple_files=True)

# --- Sensitivity Slider (Threshold) ---
threshold = st.slider(
    "Adjust Sensitivity (Higher = Less Sensitive)",
    min_value=100000,
    max_value=10000000,
    value=3000000,
    step=100000,
    help="Increase this value if you're getting too many images for minor changes. Decrease if you're missing scene changes."
)

# --- Screenshot Duration Slider ---
max_duration_sec = st.slider(
    "Screenshot Duration (seconds)",
    min_value=3,
    max_value=9,
    value=4, # Default value, currently 4 seconds
    step=1,
    help="Adjust the length of the video to analyze for scene changes (3 to 9 seconds)."
)

# --- Display Previews for Uploaded Files ---
if uploaded_files: # Check if the list of uploaded files is not empty
    st.markdown("---")
    st.subheader("Uploaded Video Previews:")
    
    # Use columns to display videos side-by-side if multiple are uploaded
    # Adjust the column count based on how many videos you want to show per row
    cols_per_row = 2 
    columns = st.columns(cols_per_row)

    for i, uploaded_file in enumerate(uploaded_files):
        # Display each video preview
        with columns[i % cols_per_row]: # Cycle through columns
            st.text(f"{uploaded_file.name}") # Show file name above video
            # NEW: Set a fixed width for the video preview
            st.video(uploaded_file, format="video/mp4", start_time=0, width=400) # Adjusted width here!

    st.markdown("---") # Separator before the processing button

    # --- Process Button ---
    if st.button("Extract Scene Screenshots from All Uploaded Videos"):
        st.subheader("Processing Results:")

        # Loop through each uploaded file to process it
        for i, uploaded_file in enumerate(uploaded_files):
            st.markdown(f"### Processing: **{uploaded_file.name}**") # Clear heading for each video's results

            # Create temporary directories for each video's processing
            # Ensures unique file paths for each video
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_video_path = os.path.join(temp_dir, uploaded_file.name)
                # Create a unique trimmed video path within the temp_dir
                temp_trimmed_video_path = os.path.join(temp_dir, f"trimmed_video_{i}.mp4")
                # Create a unique output directory for screenshots for this video
                output_screenshots_dir = os.path.join(temp_dir, f"screenshots_output_{i}")
                os.makedirs(output_screenshots_dir, exist_ok=True) # Ensure output dir exists

                # Save uploaded file to a temporary location
                with open(temp_video_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                st.info(f"Starting analysis for '{uploaded_file.name}'...")

                try:
                    # --- Trim Video to Selected Duration ---
                    st.text(f"Trimming '{uploaded_file.name}' to the first {max_duration_sec} seconds...")
                    clip = VideoFileClip(temp_video_path).subclip(0, max_duration_sec)
                    clip.write_videofile(temp_trimmed_video_path, codec='libx264', audio=False, preset='veryfast', logger=None)
                    st.success(f"'{uploaded_file.name}' trimmed successfully.")

                    # --- Process Video for Frame Changes ---
                    st.text(f"Analyzing '{uploaded_file.name}' for scene changes...")
                    cap = cv2.VideoCapture(temp_trimmed_video_path)
                    success, prev_frame = cap.read()
                    frame_count = 0
                    saved_count = 0
                    
                    # Placeholder for displaying progress
                    progress_bar = st.progress(0)
                    status_text = st.empty()

                    if not success:
                        st.error(f"Could not read '{uploaded_file.name}'. Please check its format or if it's corrupted.")
                        cap.release()
                        st.markdown("---") # Add a separator before next video
                        continue # Skip to the next uploaded file if this one fails

                    while success:
                        success, frame = cap.read()
                        if not success:
                            break
                        
                        frame_count += 1
                        
                        # Update progress bar every 10 frames or so, for smoother visual update
                        if frame_count % 10 == 0: 
                            total_frames_expected = clip.fps * max_duration_sec
                            progress_value = min(1.0, frame_count / total_frames_expected)
                            progress_bar.progress(progress_value)
                            status_text.text(f"Processing frame {frame_count} of '{uploaded_file.name}'...")

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
                            prev_frame = frame # Update prev_frame to the last saved frame to avoid multiple captures for one long change
                        else:
                            prev_frame = frame # Always update prev_frame for continuous comparison

                    cap.release()
                    progress_bar.progress(1.0)
                    status_text.text(f"Analysis complete for '{uploaded_file.name}'!")

                    st.success(f"✅ Done! Saved {saved_count} scene-change screenshots for '{uploaded_file.name}'.")

                    # --- Display Results ---
                    if saved_count > 0:
                        st.markdown("#### Extracted Scenes:")
                        # Use st.columns for better layout of images
                        cols = st.columns(4) # Display images in 4 columns per row
                        image_files = sorted([f for f in os.listdir(output_screenshots_dir) if f.endswith('.jpg')])
                        
                        for img_idx, img_file in enumerate(image_files):
                            with open(os.path.join(output_screenshots_dir, img_file), "rb") as f:
                                img_bytes = f.read()
                            cols[img_idx % 4].image(img_bytes, caption=f"Scene {img_idx+1}", use_container_width=True) # Fixed deprecation warning here too
                    else:
                        st.info(f"No significant scene changes detected for '{uploaded_file.name}' with the current sensitivity.")

                except Exception as e:
                    st.error(f"An error occurred during processing '{uploaded_file.name}': {e}")
                finally:
                    # The `tempfile.TemporaryDirectory()` context manager automatically handles cleanup
                    # of `temp_dir` and all its contents when the 'with' block exits.
                    pass
            st.markdown("---") # Add a separator after each video's results