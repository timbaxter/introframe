import streamlit as st
import cv2
import numpy as np
import os
import tempfile
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader
import gspread # For Google Sheets integration
import time # For simulating delays

# --- Streamlit App Interface (General Config) ---
st.set_page_config(page_title="Ad Scene Capture Tool", layout="wide", page_icon="📸")


# --- Configuration from config.yaml ---
# Ensure config.yaml is in the same directory as app.py
try:
    with open('config.yaml') as file:
        config = yaml.load(file, Loader=SafeLoader)
except FileNotFoundError:
    st.error("config.yaml not found. Please create it as per previous instructions.")
    st.stop() # Stop the app if config is missing

# --- Retrieve cookie key from Streamlit secrets ---
# IMPORTANT: This secret needs to be set in Streamlit Cloud dashboard.
if "cookie_key" not in st.secrets:
    st.error("Streamlit 'cookie_key' secret not found. Please set it in Streamlit Cloud's 'Secrets' section.")
    st.stop()
cookie_key_from_secrets = st.secrets["cookie_key"]


# --- Authenticator Initialization ---
authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    cookie_key_from_secrets, # Use the key fetched from st.secrets
    config['cookie']['expiry_days']
)

# --- Google Sheets Setup ---
# This part connects to your Google Sheet for user data persistence.
# It assumes you have:
# 1. Created a Google Sheet named "introFrameAppUsers" (as provided by you)
#    with columns: "username", "uses_left", "is_paid"
# 2. Created a Google Cloud Project and Service Account.
# 3. Enabled Google Sheets API and Google Drive API for that project.
# 4. Shared your Google Sheet with the service account's email (as editor).
# 5. Added the service account's JSON key content to Streamlit Cloud's Secrets
#    under the key 'gcp_service_account'.
gc = None
users_sheet = None

# ADDED DEBUGGING HERE:
try:
    st.sidebar.info("Attempting to connect to Google Sheets...")
    gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
    st.sidebar.success("gspread service account authenticated.") # Debug message
    
    spreadsheet = gc.open("introFrameAppUsers") # Your Google Sheet Name
    st.sidebar.success(f"Opened spreadsheet: {spreadsheet.title}") # Debug message
    
    users_sheet = spreadsheet.worksheet("users") # Your Google Sheet Tab Name
    st.sidebar.success(f"Selected worksheet: {users_sheet.title}") # Debug message
    
    # Optional debug:
    # st.sidebar.success("Connected to Google Sheets!")

# Changed the exception type to be more specific for actual connection errors
except gspread.exceptions.SpreadsheetNotFound:
    st.error("Google Sheet 'introFrameAppUsers' not found. Please ensure the name is exact and the service account has access.")
    st.stop()
except gspread.exceptions.WorksheetNotFound:
    st.error("Worksheet 'users' not found in 'introFrameAppUsers'. Please ensure the tab name is exact.")
    st.stop()
except gspread.exceptions.APIError as e: # Catch specific API errors from gspread
    st.error(f"Google Sheets API error: {e}. Check Google Cloud API permissions and propagation.")
    st.stop()
except KeyError:
    st.error("Google Cloud Platform service account secrets ('gcp_service_account') not found. Please set them in Streamlit Cloud's 'Secrets' section.")
    st.stop()
except Exception as e: # Catch any other unexpected errors during connection
    st.error(f"An unexpected error occurred during Google Sheets setup: {e}")
    st.stop()


# --- Google Sheets Helper Functions ---
def load_user_data_from_gsheets():
    """Loads all user records from the Google Sheet into a dictionary."""
    try:
        records = users_sheet.get_all_records()
        return records_to_dict(records) # Use helper for conversion
    except Exception as e:
        st.error(f"Error loading user data from Google Sheet: {e}")
        return {} # Return empty dict on error to prevent app crash

def records_to_dict(records):
    """Converts a list of gspread records to a dictionary keyed by username."""
    user_dict = {}
    for record in records:
        # Ensure 'uses_left' is an int and 'is_paid' is a boolean
        try:
            record['uses_left'] = int(record['uses_left'])
            record['is_paid'] = str(record['is_paid']).lower() == 'true'
        except (ValueError, KeyError):
            st.warning(f"Skipping malformed user record: {record}")
            continue
        user_dict[record['username']] = {'uses_left': record['uses_left'], 'is_paid': record['is_paid']}
    return user_dict

def save_user_data_to_gsheets(username, uses_left, is_paid):
    """Updates a user's data in the Google Sheet or appends if new."""
    try:
        # Fetch current records to find the row index
        records = users_sheet.get_all_records()
        usernames_list = [r['username'] for r in records]

        if username in usernames_list:
            # User exists, update the row
            row_index = usernames_list.index(username) + 2 # +2 because gspread is 1-indexed and has a header row
            users_sheet.update_cell(row_index, 2, uses_left) # Column B is 'uses_left'
            users_sheet.update_cell(row_index, 3, is_paid)   # Column C is 'is_paid'
        else:
            # New user, append a new row with initial values
            users_sheet.append_row([username, uses_left, is_paid])
    except Exception as e:
        st.error(f"Error saving user data to Google Sheet: {e}")


# --- Main Streamlit App Logic (wrapped by authentication) ---

# Define the login location explicitly in a variable
login_location = 'main' 
name, authentication_status, username = authenticator.login('Login', login_location) # Pass the variable


# --- Conditional Content based on Authentication Status ---
if authentication_status:
    # User is logged in
    authenticator.logout('Logout', 'sidebar') # Display logout button in sidebar
    st.sidebar.title(f"Welcome {name}") # Display welcome message in sidebar

    # Load all user data from Google Sheets to get current user's status
    # Ensure users_sheet is not None before attempting to load data
    if users_sheet is not None:
        all_users_data = load_user_data_from_gsheets()
    else:
        st.error("Google Sheets is not initialized. Cannot load user data.")
        all_users_data = {} # Fallback to empty data to prevent further errors
        st.stop()


    current_user_data = all_users_data.get(username, None)

    # Initialize user in Google Sheet if they are logging in for the very first time
    if current_user_data is None:
        initial_uses = 3
        save_user_data_to_gsheets(username, initial_uses, False) # Give 3 free uses
        current_user_data = {'uses_left': initial_uses, 'is_paid': False} # Update in-memory for current session

    uses_left = current_user_data['uses_left']
    is_paid = current_user_data['is_paid']

    # --- Main Application Title & Description ---
    st.title("📸 Facebook Ad Scene Capture")
    st.markdown("Upload your MP4 ad(s), and I'll extract key scene changes from the first few seconds!")

    # --- Conditional Access (Free Trial / Paid Access) ---
    if is_paid or uses_left > 0:
        if not is_paid: # Only show uses left if not a paid user
            st.info(f"You have {uses_left} free uses remaining.")
        else:
            st.success("You have unlimited access! �")

        # --- File Uploader (Your original code starts here) ---
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
            value=4, # Default value
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

                # Loop through each uploaded file to process it
                for i, uploaded_file in enumerate(uploaded_files):
                    st.markdown(f"### Processing: **{uploaded_file.name}**")

                    # Create temporary directories for each video's processing
                    with tempfile.TemporaryDirectory() as temp_dir:
                        temp_video_path = os.path.join(temp_dir, uploaded_file.name)
                        output_screenshots_dir = os.path.join(temp_dir, f"screenshots_output_{i}")
                        os.makedirs(output_screenshots_dir, exist_ok=True)

                        # Save uploaded file to a temporary location
                        with open(temp_video_path, "wb") as f:
                            f.write(uploaded_file.getbuffer())
                        st.info(f"Starting analysis for '{uploaded_file.name}'...")

                        try:
                            # --- MODIFIED: Video Processing using OpenCV ONLY, no MoviePy ---
                            
                            # OpenCV Video Capture
                            cap = cv2.VideoCapture(temp_video_path)
                            if not cap.isOpened():
                                st.error(f"Could not open video file '{uploaded_file.name}'. Please check its format or if it's corrupted.")
                                st.markdown("---")
                                continue # Skip to the next uploaded file

                            fps = cap.get(cv2.CAP_PROP_FPS)
                            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                            duration_video = total_frames / fps
                            
                            # Determine actual frames to process based on max_duration_sec
                            frames_to_process = int(fps * max_duration_sec)
                            if frames_to_process > total_frames:
                                frames_to_process = total_frames # Don't go beyond actual video length

                            st.text(f"Analyzing '{uploaded_file.name}' (first {min(duration_video, max_duration_sec):.1f} seconds / {frames_to_process} frames)...")
                            
                            success, prev_frame = cap.read()
                            frame_count = 0
                            saved_count = 0
                            
                            progress_bar = st.progress(0)
                            status_text = st.empty()

                            while success and frame_count < frames_to_process: # Only process up to max_duration_sec
                                success, frame = cap.read()
                                if not success:
                                    break
                                
                                frame_count += 1
                                
                                # Update progress bar
                                progress_value = min(1.0, frame_count / frames_to_process)
                                progress_bar.progress(progress_value)
                                status_text.text(f"Processing frame {frame_count} of {frames_to_process} for '{uploaded_file.name}'...")

                                if frame_count == 1: # No previous frame for first one
                                    prev_frame = frame
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
                                    # For subsequent comparison, use the frame *after* the change
                                    # to detect *new* changes, not small variations on the same scene.
                                    prev_frame = frame 
                                else:
                                    prev_frame = frame # Always update prev_frame for continuous comparison

                            cap.release()
                            progress_bar.progress(1.0)
                            status_text.text(f"Analysis complete for '{uploaded_file.name}'!")

                            st.success(f"✅ Done! Saved {saved_count} scene-change screenshots for '{uploaded_file.name}'.")

                            # --- DISPLAYING RESULTS ---
                            if saved_count > 0:
                                st.markdown("#### Extracted Scenes:")
                                cols = st.columns(4) # Display images in 4 columns per row
                                image_files = sorted([f for f in os.listdir(output_screenshots_dir) if f.endswith('.jpg')])
                                
                                for img_idx, img_file in enumerate(image_files):
                                    with open(os.path.join(output_screenshots_dir, img_file), "rb") as f:
                                        img_bytes = f.read()
                                    cols[img_idx % 4].image(img_bytes, caption=f"Scene {img_idx+1}", use_container_width=True)
                            else:
                                st.info(f"No significant scene changes detected for '{uploaded_file.name}' with the current sensitivity.")


                            # IMPORTANT: After your actual screenshot code runs successfully for a free user,
                            # decrement their usage.
                            if not is_paid: # Only decrement for free users
                                save_user_data_to_gsheets(username, uses_left - 1, is_paid)
                                # Rerun to update uses_left count in the UI for the current user
                                st.experimental_rerun() 
                            else:
                                st.success("Screenshot generated successfully!") # For paid users, no decrement needed


                        except Exception as e:
                            st.error(f"An error occurred during processing '{uploaded_file.name}': {e}")
                        finally:
                            pass # TemporaryDirectory handles cleanup

                    st.markdown("---") # Separator after each video's results


    else: # User has no free uses left and is not a paid user
        st.error("You have used all your free uses.")
        st.info("Please purchase a plan to continue using the tool.")

        # --- Purchase Button (for Stripe integration) ---
        # Replace 'https://buy.stripe.com/YOUR_PAYMENT_LINK' with the actual payment link from Stripe.
        # This link will be created in Phase 3.
        stripe_payment_link = "https://buy.stripe.com/4gM28qa6lb5xcWO5Gi38400" # Your Stripe Payment Link
        
        if st.button("Purchase Unlimited Access"):
            st.markdown(f'[<p style="text-align: center; color: white; background-color: #6264ff; padding: 10px; border-radius: 5px; text-decoration: none;">Click Here to Purchase Unlimited Access!</p>]({stripe_payment_link})', unsafe_allow_html=True)
            st.info("You will be redirected to a secure Stripe page to complete your purchase.")


elif authentication_status == False:
    # User entered incorrect credentials
    st.error('Username/password is incorrect')
elif authentication_status == None:
    # User is not logged in yet
    st.warning('Please enter your username and password to access the tool.')
    st.info("No account? Use the login credentials from your `config.yaml` file for now (e.g., username: `admin_user`, password: `your_secure_password`).")

# --- Optional: User Registration ---
# Uncomment this block if you want to allow self-registration.
# Be aware: If you enable this and use config.yaml for storage, new users
# will be written to config.yaml. For deployed apps, this file is generally read-only
# or ephemeral on Streamlit Cloud. For dynamic registration, you'd need to modify this
# to save directly to your Google Sheet after successful registration.
# try:
#     if authenticator.register_user('Register new user', 'main'):
#         st.success('User registered successfully! Please login.')
#         # NOTE: For Google Sheets persistence, you would typically add logic here
#         # to also add the newly registered user to your Google Sheet with initial uses.
#         # You'd need to retrieve the newly registered username/email after registration.
# except Exception as e:
#     st.error(e)
