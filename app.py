import streamlit as st
import cv2
import numpy as np
import os
import tempfile
import yaml
import gspread
import time
import bcrypt # Import bcrypt for hashing/checking passwords

# --- Streamlit App Interface (General Config) ---
st.set_page_config(page_title="Ad Scene Capture Tool", layout="wide", page_icon="📸")


# --- Configuration from config.yaml ---
# config.yaml now ONLY contains usernames and their hashed passwords.
# No cookie info or preauthorized list needed here, as we manage cookies manually.
try:
    with open('config.yaml') as file:
        config = yaml.load(file, Loader=SafeLoader)
except FileNotFoundError:
    st.error("config.yaml not found. Please create it as per previous instructions.")
    st.stop()


# --- Google Sheets Setup ---
# Your existing Google Sheets setup remains the same.
gc = None
users_sheet = None

try:
    gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
    spreadsheet = gc.open("introFrameAppUsers") 
    users_sheet = spreadsheet.worksheet("users") 
    
except gspread.exceptions.SpreadsheetNotFound:
    st.error("Google Sheet 'introFrameAppUsers' not found. Please ensure the name is exact and the service account has access.")
    st.stop()
except gspread.exceptions.WorksheetNotFound:
    st.error("Worksheet 'users' not found in 'introFrameAppUsers'. Please ensure the tab name is exact.")
    st.stop()
except gspread.exceptions.APIError as e:
    st.error(f"Google Sheets API error: {e}. Check Google Cloud API permissions and propagation.")
    st.stop()
except KeyError:
    st.error("Google Cloud Platform service account secrets ('gcp_service_account') not found. Please set them in Streamlit Cloud's 'Secrets' section.")
    st.stop()
except Exception as e:
    st.error(f"An unexpected error occurred during Google Sheets setup: {e}")
    st.stop()


# --- Google Sheets Helper Functions ---
def load_user_data_from_gsheets():
    """Loads all user records from the Google Sheet into a dictionary."""
    try:
        records = users_sheet.get_all_records()
        user_data_dict = {}
        for record in records:
            try:
                user_data_dict[record['username']] = {
                    'uses_left': int(record['uses_left']),
                    'is_paid': str(record['is_paid']).lower() == 'true',
                    'email': record.get('email', '') # Ensure email is pulled if it exists
                }
            except (ValueError, KeyError) as e:
                st.warning(f"Skipping malformed user record in Google Sheet: {record} - Error: {e}")
                continue
        return user_data_dict
    except Exception as e:
        st.error(f"Error loading user data from Google Sheet: {e}")
        return {}

def save_user_data_to_gsheets(username, uses_left, is_paid, email):
    """Updates a user's data in the Google Sheet or appends if new."""
    try:
        records = users_sheet.get_all_records()
        usernames_list = [r['username'] for r in records]

        if username in usernames_list:
            row_index = usernames_list.index(username) + 2
            users_sheet.update_cell(row_index, 2, uses_left) # uses_left is Column B
            users_sheet.update_cell(row_index, 3, is_paid)   # is_paid is Column C
            # Assuming 'email' is in Column D if you want to store it there later
            # users_sheet.update_cell(row_index, 4, email) 
        else:
            # New user, append a new row
            users_sheet.append_row([username, uses_left, is_paid, email]) # Add email if you plan to store it
    except Exception as e:
        st.error(f"Error saving user data to Google Sheet: {e}")


# --- Custom Login/Registration Logic ---

# Initialize session state for login/auth
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'username' not in st.session_state:
    st.session_state.username = None
if 'current_view' not in st.session_state:
    st.session_state.current_view = 'login' # 'login' or 'register'

def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(password, hashed_password):
    return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))


# --- Main App Flow ---

# If user is authenticated, show the main application
if st.session_state.authenticated:
    username = st.session_state.username
    # config['credentials']['usernames'] is loaded from config.yaml
    # Check if username exists in loaded config data before accessing
    if username in config['credentials']['usernames']:
        name = config['credentials']['usernames'][username].get('name', username) # Get display name
    else:
        # This case handles if a user logs in but their data isn't in config.yaml
        # (e.g., if config.yaml was reset or they registered only to GSheets)
        # For simplicity, we'll just use username as name.
        name = username 

    # Display logout button in sidebar
    with st.sidebar:
        st.title(f"Welcome {name}") 
        if st.button("Logout"):
            st.session_state.authenticated = False
            st.session_state.username = None
            st.rerun()

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
    # (This catches users registered manually or through the new form if GSheets save failed on registration)
    if current_user_data is None:
        initial_uses = 3
        # Assuming your Google Sheet has an 'email' column or similar to store this
        # Otherwise, adjust save_user_data_to_gsheets to match your sheet structure.
        user_email_for_gsheet = config['credentials']['usernames'][username].get('email', '')
        save_user_data_to_gsheets(username, initial_uses, False, user_email_for_gsheet) 
        current_user_data = {'uses_left': initial_uses, 'is_paid': False}

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
            st.sidebar.markdown("<p style='color: #28a745; font-weight: bold;'>You have unlimited access! 🎉</p>", unsafe_allow_html=True) # Changed from st.sidebar.success to st.sidebar.markdown for no green background

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
                        # Removed debug info message: st.info(f"Starting analysis for '{uploaded_file.name}'...")

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

                            # Removed debug text: st.text(f"Analyzing '{uploaded_file.name}' (first {min(duration_video, max_duration_sec):.1f} seconds / {frames_to_process} frames)...")
                            
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
                                status_text.text(f"Processing frame {frame_count} of {frames_to_process} for '{uploaded_file.name}'...") # Keep this for live feedback

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
                            status_text.text(f"Analysis complete for '{uploaded_file.name}'!") # Keep this for final feedback

                            st.success(f"✅ Done! Saved {saved_count} scene-change screenshots for '{uploaded_file.name}'.") # Keep this

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
                                st.rerun() # Using st.rerun() now, not experimental
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
            st.info("You will be redirected to a secure Stripe page to complete your purchase.") # Kept as user-facing info

# Else: User is NOT authenticated, show login and registration forms
else: 
    st.title("Welcome to Ad Scene Capture Tool!")
    st.markdown("Unlock key insights from your video ads in seconds.")

    st.subheader("Login to Your Account")
    # Login Form
    with st.form("login_form"):
        login_username = st.text_input("Username", key="login_username_input_public")
        login_password = st.text_input("Password", type="password", key="login_password_input_public")
        login_button = st.form_submit_button("Login")

        if login_button:
            # Load users from config.yaml for login
            user_creds = config['credentials']['usernames']
            if login_username in user_creds:
                stored_hashed_password = user_creds[login_username]['password']
                # Check if the stored password is a hash (starts with $2b$12$)
                if stored_hashed_password.startswith('$2b$12$'):
                    if bcrypt.checkpw(login_password.encode('utf-8'), stored_hashed_password.encode('utf-8')):
                        st.session_state.authenticated = True
                        st.session_state.username = login_username
                        st.success("Logged in successfully! Rerunning app...")
                        st.rerun() # Rerun to display main app
                    else:
                        st.error("Incorrect username or password.")
                else: # Fallback for non-hashed passwords if you have any in config.yaml for testing
                    if login_password == stored_hashed_password:
                        st.session_state.authenticated = True
                        st.session_state.username = login_username
                        st.success("Logged in successfully! Rerunning app...")
                        st.rerun()
                    else:
                        st.error("Incorrect username or password.")
            else:
                st.error("Incorrect username or password.")

    st.markdown("---") # Separator between login and register

    st.subheader("New to the Ad Scene Capture Tool? Register for a Free Trial!")
    # Registration Form
    with st.form("register_form"):
        reg_username = st.text_input("Choose a Username", key="reg_username_input")
        reg_email = st.text_input("Your Email", key="reg_email_input")
        reg_password = st.text_input("Choose a Password", type="password", key="reg_password_input")
        reg_password_confirm = st.text_input("Confirm Password", type="password", key="reg_password_confirm_input")
        register_button = st.form_submit_button("Register")

        if register_button:
            user_creds = config['credentials']['usernames']
            if reg_username in user_creds:
                st.error("Username already exists. Please choose a different one.")
            elif not reg_username or not reg_email or not reg_password or not reg_password_confirm:
                st.error("All registration fields are required.")
            elif reg_password != reg_password_confirm:
                st.error("Passwords do not match.")
            else:
                # Hash the new password
                hashed_new_password = bcrypt.hashpw(reg_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                
                # IMPORTANT: Update config dictionary in memory (this is temporary for Streamlit Cloud)
                # For persistence, we need to save to Google Sheets immediately.
                config['credentials']['usernames'][reg_username] = {
                    'email': reg_email,
                    'name': reg_username, # Use username as display name initially
                    'password': hashed_new_password
                }
                
                st.success("Registration successful! Attempting to set up your free trial...")
                
                # Directly save new user to Google Sheet with 3 uses on registration
                try:
                    # Make sure your Google Sheet has an 'email' column (e.g., as column D)
                    save_user_data_to_gsheets(reg_username, 3, False, reg_email)
                    st.success("Your free trial account has been set up in our system! Please login above with your new username and password.")
                except Exception as e:
                    st.error(f"Could not save registration to Google Sheet: {e}. Please try logging in, and if the issue persists, contact support.")

