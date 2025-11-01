"""
This module defines the graphical user interface (GUI) for the CareLog application using Streamlit.

It includes functions for rendering all UI components, such as authentication pages (login, register),
role-specific dashboards (patient, clinician, admin), and various features like patient note management,
secure messaging, and administrative tasks.

The main entry point for the UI is `show_main_app`, which routes the user to the appropriate
view based on their authentication status and role.
"""
# carelog/gui.py

import streamlit as st
from modules.models import PatientNote
import json
import datetime
import time
import pandas as pd

# Attempt to import streamlit_autorefresh for automatic page refreshing.
# If unavailable, fall back to a manual refresh mechanism.
try:
    from streamlit_autorefresh import st_autorefresh as _st_autorefresh
except ImportError:
    _st_autorefresh = getattr(st, "autorefresh", None)

# Constants
CHAT_REFRESH_INTERVAL_SECONDS = 3.0

def _rerun():
    """Triggers a rerun of the Streamlit app to refresh the UI.

    This function attempts to use the modern `st.rerun()` if available,
    falling back to the older `st.experimental_rerun()` for compatibility.
    """
    rerun_callable = getattr(st, "experimental_rerun", None)
    if callable(rerun_callable):
        rerun_callable()
    else:
        st.rerun()

def _format_timestamp(timestamp_str):
    """Converts an ISO 8601 timestamp string into a human-readable local time format.

    Args:
        timestamp_str (str): The ISO-formatted timestamp string.

    Returns:
        str: A formatted string (e.g., "Jan 01, 2023 • 14:30") or the original
             string if conversion fails.
    """
    if not timestamp_str:
        return "Unknown time"
    try:
        # Ensure the 'Z' is replaced with a UTC offset for consistent parsing.
        clean_value = timestamp_str.replace('Z', '+00:00')
        timestamp = datetime.datetime.fromisoformat(clean_value)
        # If no timezone is present, assume UTC.
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=datetime.timezone.utc)
        # Convert to the user's local timezone.
        local_timestamp = timestamp.astimezone()
        return local_timestamp.strftime("%b %d, %Y • %H:%M")
    except ValueError:
        return timestamp_str

def _get_display_name(service, hospital_id, username, role, cache):
    """Retrieves the full name of a user for display, using a cache to minimize lookups.

    Args:
        service: The main application service instance.
        hospital_id (str): The ID of the hospital.
        username (str): The user's username.
        role (str): The user's role.
        cache (dict): A dictionary used for caching display names.

    Returns:
        str: The user's full name, or their username if the full name is not available.
    """
    cache_key = (username, role)
    if cache_key in cache:
        return cache[cache_key]
    user_data = service.get_user_by_username(hospital_id, username, role)
    display_name = user_data.get('full_name') if user_data else None
    if not display_name:
        display_name = username
    cache[cache_key] = display_name
    return display_name

def _render_chat_messages(service, hospital_id, messages):
    """Displays a list of chat messages in a scrollable container.

    Args:
        service: The main application service instance.
        hospital_id (str): The ID of the hospital.
        messages (list): A list of message dictionaries to display.
    """
    if not messages:
        st.info("No messages yet. Start the conversation below.")
        return

    name_cache = {}
    chat_container = st.container()
    with chat_container:
        # Custom CSS to create a scrollable chat history.
        st.markdown(
            """
            <style>
            div[data-testid="chat-history-wrapper"] {
                max-height: 350px;
                overflow-y: auto;
                padding-right: 12px;
            }
            div[data-testid="chat-history-wrapper"]::-webkit-scrollbar {
                width: 8px;
            }
            div[data-testid="chat-history-wrapper"]::-webkit-scrollbar-thumb {
                background-color: rgba(155, 155, 155, 0.4);
                border-radius: 4px;
            }
            </style>
            """,
            unsafe_allow_html=True
        )
        # Render each message in a chat bubble.
        chat_wrapper = st.markdown('<div data-testid="chat-history-wrapper">', unsafe_allow_html=True)
        for message in messages:
            sender = message.get('sender')
            role = message.get('sender_role', 'patient')
            display_name = _get_display_name(service, hospital_id, sender, role, name_cache)
            role_label = "Patient" if role == 'patient' else 'Clinician'
            timestamp_display = _format_timestamp(message.get('timestamp'))
            bubble_role = "user" if role == 'patient' else 'assistant'
            avatar = "🙂" if role == 'patient' else "🩺"

            with st.chat_message(bubble_role, avatar=avatar):
                st.markdown(f"**{display_name}** · {role_label}")
                st.write(message.get('text', ''))
                st.caption(timestamp_display)
        st.markdown('</div>', unsafe_allow_html=True)

# Page navigation helpers
def set_page_welcome():
    """Sets the session state to display the welcome page."""
    st.session_state.auth_page = 'welcome'

def set_page_login():
    """Sets the session state to display the login page."""
    st.session_state.auth_page = 'login'

def set_page_register():
    """Sets the session state to display the registration page."""
    st.session_state.auth_page = 'register'

# Authentication Pages
def show_welcome_page():
    """Displays the main welcome screen with login and registration options."""
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<h1 style='text-align: center;'>Welcome to CareLog </h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center;'>A multi-hospital platform for patient care.</p>", unsafe_allow_html=True)
        st.info("To begin, please select an option below. You will be asked for your hospital's unique ID.")
        
        st.button("Login to an Existing Account", on_click=set_page_login, use_container_width=True, type="primary")
        st.button("Create a New Account", on_click=set_page_register, use_container_width=True)

def show_login_form(service):
    """Displays the login form and handles user authentication.

    Args:
        service: The main application service instance.
    """
    st.button("← Back to Welcome", on_click=set_page_welcome)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<h2 style='text-align: center;'>Account Login</h2>", unsafe_allow_html=True)
        with st.form("login_form"):
            hospital_id = st.text_input("Hospital ID", help="Enter the unique ID for your hospital.")
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            role = st.selectbox("Login as", ["patient", "clinician", "admin"])
            submitted = st.form_submit_button("Login", use_container_width=True)

            if submitted:
                if not hospital_id or not username or not password:
                    st.error("Hospital ID, Username, and Password are required.")
                else:
                    with st.spinner("Logging in..."):
                        time.sleep(1) # Simulate network latency
                        user = service.login(username, password, role, hospital_id)
                        if user == 'pending':
                            st.warning("Your account creation is successful but is pending approval by an administrator.")
                        elif user:
                            # On successful login, store user info in session and rerun.
                            st.session_state.current_user = user
                            st.session_state.hospital_id = hospital_id
                            st.session_state.auth_page = 'welcome'
                            st.rerun()
                        else:
                            st.error("Invalid credentials for the selected role.")
                    
def show_register_form(service):
    """Displays the user registration form and handles new account creation.

    Args:
        service: The main application service instance.
    """
    st.button("← Back to Welcome", on_click=set_page_welcome)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<h2 style='text-align: center;'>Create a New Account</h2>", unsafe_allow_html=True)
        with st.form("register_form"):
            full_name = st.text_input("Full Name")
            role = st.selectbox("Select your role", ["patient", "clinician", "admin"])
            hospital_id = st.text_input("Hospital ID", help="If your hospital is new, this will create it. If it exists, you will join it.")
            username = st.text_input("Choose a Username")
            password = st.text_input(
                "Choose a Password",
                type="password",
                help="Use at least 8 characters with uppercase, lowercase, number, and symbol."
            )
            
            st.markdown("---")
            dob = st.date_input("Date of Birth", min_value=datetime.date(1900, 1, 1))
            sex = st.selectbox("Sex", ["Male", "Female", "Intersex", "Prefer not to say"])
            pronouns = st.text_input("Pronouns (e.g., she/her, they/them)")
            bio = st.text_area("Bio (Optional)")

            submitted = st.form_submit_button("Register", use_container_width=True)

            if submitted:
                if not hospital_id or not username or not password or not full_name:
                    st.error("All fields are required.")
                else:
                    with st.spinner("Registering..."):
                        time.sleep(1) # Simulate processing time
                        result = service.register_user(username, password, role, hospital_id, full_name, dob.isoformat(), sex, pronouns, bio)
                        if result == 'weak_password':
                            st.error("Password must be at least 8 characters and include uppercase, lowercase, number, and symbol.")
                        elif result == 'pending':
                            st.info("Your account registration is successful but pending approval by an administrator.")
                        elif result == 'hospital_not_found':
                            st.error(f"Hospital with ID {hospital_id} does not exist. An admin must create it first.")
                        elif result:
                            st.success(f"User {username} registered for {hospital_id}! Please go back to log in.")
                        else:
                            st.error(f"A profile for username {username} with the role {role} already exists at this hospital.")

# Main Application UI
def show_main_app(service):
    """
    The main application router that displays the correct UI based on the user's role.

    This function acts as the central hub after a user logs in, directing them
    to the appropriate dashboard (Clinician, Patient, or Admin).

    Args:
        service: The main application service instance.
    """
    user = st.session_state.current_user
    hospital_id = st.session_state.hospital_id

    # Initialize the page state if it doesn't exist.
    if 'page' not in st.session_state:
        st.session_state.page = None

    # Reset page state if the user's role changes or on the first load.
    if 'current_role' not in st.session_state or st.session_state.current_role != user.role:
        st.session_state.page = None
        st.session_state.current_role = user.role

    menu_placeholder = st.empty()

    def _show_main_menu(options, title, banner_message=None):
        """
        Renders the main menu for a given user role.

        Args:
            options (list): A list of tuples, where each tuple contains the
                            label, page key, and description for a menu item.
            title (str): The title of the menu (e.g., "Clinician Dashboard").
            banner_message (str, optional): A message to display as a warning banner.
        """
        with menu_placeholder.container():
            if banner_message:
                st.warning(banner_message)
            st.markdown(f"## {title} — {user.full_name or user.username}")
            st.caption(f"Hospital ID: {hospital_id}")
            st.divider()
            # Custom styling for menu buttons.
            st.markdown(
                """
                <style>
                div.stButton > button {
                    background-color: #3883eb !important;
                    color: #ffffff !important;
                    border-color: #3883eb !important;
                }
                div.stButton > button:hover {
                    filter: brightness(0.95);
                }
                </style>
                """,
                unsafe_allow_html=True
            )
            # Create a button for each menu option.
            for idx, (label, value, description) in enumerate(options):
                button_key = f"{user.role}_menu_btn_{idx}"
                if st.button(label, key=button_key, use_container_width=True):
                    st.session_state.page = value
                    st.rerun()
                st.caption(description)
                st.divider()
            # Logout button.
            if st.button("Log Out", key=f"{user.role}_logout_btn", use_container_width=True):
                with st.spinner("Logging out..."):
                    time.sleep(1)
                    service.logout()
                    st.session_state.current_user = None
                    st.session_state.hospital_id = None
                    st.session_state.auth_page = 'welcome'
                    st.rerun()

    def _show_back_button():
        """Renders a button to navigate back to the main menu."""
        if st.button("← Back to Main Menu"):
            st.session_state.page = None
            st.rerun()

    # Role-based routing for the main application.
    if user.role == 'clinician':
        menu_items = [
            ("View Notes", "clinician_view_notes", "Browse patients' histories, search within notes, and review profiles."),
            ("Add Note", "clinician_add_note", "Log a new clinical observation for any assigned patient."),
            ("Messaging", "clinician_messaging", "Chat with patients in real time or leave care-team updates."),
            ("AI Feedback", "clinician_feedback", "Review and finalize AI-generated responses before sending."),
            ("Pain Alerts", "clinician_alerts", "Respond to any critical 10/10 pain alerts reported by patients."),
            ("My Profile", "clinician_profile", "Update your personal and professional details."),
        ]
        if st.session_state.page is None:
            alerts = service.get_pain_alerts(hospital_id)
            banner = f"🚨 {len(alerts)} high-priority alerts awaiting review." if alerts else None
            _show_main_menu(menu_items, "Clinician Dashboard", banner_message=banner)
            return
        else:
            menu_placeholder.empty()

        # Sub-page routing for the clinician dashboard.
        if st.session_state.page == "clinician_view_notes":
            _show_back_button()
            _render_view_notes_page(service, hospital_id)
        elif st.session_state.page == "clinician_add_note":
            _show_back_button()
            _render_add_note_page(service, hospital_id)
        elif st.session_state.page == "clinician_messaging":
            _show_back_button()
            _render_clinician_chat_page(service, hospital_id)
        elif st.session_state.page == "clinician_feedback":
            _show_back_button()
            _render_review_feedback_page(service, hospital_id)
        elif st.session_state.page == "clinician_alerts":
            _show_back_button()
            _render_pain_alerts_page(service, hospital_id)
        elif st.session_state.page == "clinician_profile":
            _show_back_button()
            _render_profile_page(service, hospital_id)
        else:
            st.session_state.page = None
            st.rerun()

    elif user.role == 'patient':
        menu_items = [
            ("Add Entry", "patient_add_entry", "Log how you feel today, including mood, pain, and appetite."),
            ("View Notes", "patient_view_notes", "See your full care history and any clinician notes."),
            ("Messaging", "patient_messaging", "Reach your care team or chat privately with assigned clinicians."),
            ("My Profile", "patient_profile", "Edit your personal information and preferences."),
        ]
        if st.session_state.page is None:
            _show_main_menu(menu_items, "Patient Hub")
            return
        else:
            menu_placeholder.empty()

        # Sub-page routing for the patient hub.
        if st.session_state.page == "patient_add_entry":
            _show_back_button()
            _render_add_patient_entry_page(service, hospital_id)
        elif st.session_state.page == "patient_view_notes":
            _show_back_button()
            _render_view_notes_page(service, hospital_id, patient_id=user.username)
        elif st.session_state.page == "patient_messaging":
            _show_back_button()
            _render_patient_chat_page(service, hospital_id)
        elif st.session_state.page == "patient_profile":
            _show_back_button()
            _render_profile_page(service, hospital_id)
        else:
            st.session_state.page = None
            st.rerun()

    elif user.role == 'admin':
        menu_items = [
            ("User Management", "admin_users", "Approve new users, edit accounts, and export hospital data."),
            ("Assign Clinicians", "admin_assign", "Pair clinicians with patients to streamline communication."),
            ("My Profile", "admin_profile", "Maintain your administrator account details."),
        ]
        if st.session_state.page is None:
            _show_main_menu(menu_items, "Admin Console")
            return
        else:
            menu_placeholder.empty()

        # Sub-page routing for the admin console.
        if st.session_state.page == "admin_users":
            _show_back_button()
            _render_admin_page(service, hospital_id)
        elif st.session_state.page == "admin_assign":
            _show_back_button()
            _render_assign_clinicians_page(service, hospital_id)
        elif st.session_state.page == "admin_profile":
            _show_back_button()
            _render_profile_page(service, hospital_id)
        else:
            st.session_state.page = None
            st.rerun()

def _render_profile_page(service, hospital_id):
    """Renders the user profile page for viewing and editing personal details.

    Args:
        service: The main application service instance.
        hospital_id (str): The ID of the hospital.
    """
    st.markdown("<h2 style='text-align: center;'>My Profile</h2>", unsafe_allow_html=True)
    user = st.session_state.current_user
    user_data = service.get_all_users(hospital_id).get(f"{user.username}_{user.role}")

    if not user_data:
        st.error("Could not load user profile.")
        return

    # Profile editing form.
    with st.form("profile_form"):
        st.write(f"**Username:** {user_data['username']}")
        st.write(f"**Role:** {user_data['role'].capitalize()}")

        full_name = st.text_input("Full Name", value=user_data.get('full_name', ''))
        
        dob_val = user_data.get('dob')
        dob = st.date_input("Date of Birth", value=datetime.date.fromisoformat(dob_val) if dob_val else None, min_value=datetime.date(1900, 1, 1))
        
        sex_options = ["Male", "Female", "Intersex", "Prefer not to say"]
        sex = st.selectbox("Sex", options=sex_options, index=sex_options.index(user_data.get('sex')) if user_data.get('sex') in sex_options else 0)
        
        pronouns = st.text_input("Pronouns", value=user_data.get('pronouns', ''))
        bio = st.text_area("Bio", value=user_data.get('bio', ''))

        st.markdown("---")
        st.subheader("Change Password")
        new_password = st.text_input("New Password (leave blank to keep current password)", type="password")

        submitted = st.form_submit_button("Update Profile")
        if submitted:
            update_details = {
                "full_name": full_name, "dob": dob.isoformat() if dob else None, "sex": sex,
                "pronouns": pronouns, "bio": bio, "new_password": new_password
            }
            with st.spinner("Updating profile..."):
                time.sleep(1)
                if service.update_user_profile(hospital_id, user.username, user.role, update_details):
                    st.success("Profile updated successfully!")
                else:
                    st.error("Failed to update profile.")

    # "Danger Zone" for account deletion.
    st.divider()
    st.error("Danger Zone")
    st.write("Deleting your account will permanently remove your access and associated data permitted for your role.")
    confirm_delete = st.checkbox("I understand this action cannot be undone.", key="confirm_delete_account")
    delete_disabled = not confirm_delete
    if st.button("Delete My Account", type="secondary", disabled=delete_disabled):
        with st.spinner("Deleting account..."):
            if service.delete_user(hospital_id, user.username, user.role):
                st.success("Your account has been deleted.")
                service.logout()
                st.session_state.current_user = None
                st.session_state.hospital_id = None
                st.session_state.auth_page = 'welcome'
                st.rerun()
            else:
                st.error("Unable to delete your account. Please contact an administrator.")

def _display_user_profile_details(user_data):
    """Renders a read-only view of a user's profile details.

    Args:
        user_data (dict): A dictionary containing the user's profile information.
    """
    st.write(f"**Username:** {user_data.get('username', 'N/A')}")
    st.write(f"**Role:** {user_data.get('role', 'N/A').capitalize()}")
    st.write(f"**Full Name:** {user_data.get('full_name', 'N/A')}")
    
    dob_val = user_data.get('dob')
    dob_display = datetime.date.fromisoformat(dob_val).strftime('%B %d, %Y') if dob_val else "N/A"
    st.write(f"**Date of Birth:** {dob_display}")
    
    st.write(f"**Sex:** {user_data.get('sex', 'N/A')}")
    st.write(f"**Pronouns:** {user_data.get('pronouns', 'N/A')}")
    st.write(f"**Bio:**")
    st.info(user_data.get('bio') or "_No bio provided._")

def _schedule_auto_refresh(key, interval_seconds=CHAT_REFRESH_INTERVAL_SECONDS, expected_page=None):
    """Schedules a periodic rerun of the app to keep chat feeds fresh.

    Args:
        key (str): A unique key for the autorefresh component.
        interval_seconds (float): The refresh interval in seconds.
        expected_page (str, optional): If provided, the refresh will only occur
                                       if the session is on this page.
    """
    interval_ms = int(interval_seconds * 1000)
    if _st_autorefresh:
        _st_autorefresh(interval=interval_ms, key=key)
        st.caption(f"Chat updates automatically every {int(interval_seconds)} seconds.")
        return

    # Fallback mechanism if st_autorefresh is not available.
    st.caption(f"Chat updates automatically every {int(interval_seconds)} seconds.")
    if expected_page is not None and st.session_state.get('page') != expected_page:
        return
    time.sleep(interval_seconds)
    if expected_page is not None and st.session_state.get('page') != expected_page:
        return
    _rerun()

def _render_patient_chat_page(service, hospital_id):
    """Renders the patient's secure messaging interface.

    Args:
        service: The main application service instance.
        hospital_id (str): The ID of the hospital.
    """
    st.markdown("<h2 style='text-align: center;'>Secure Messaging</h2>", unsafe_allow_html=True)
    chat_service = getattr(service, 'chat', None)
    if not chat_service:
        st.error("Chat service is currently unavailable.")
        return

    user = st.session_state.current_user
    st.info("Use the care team channel to reach any approved clinician. Direct messages go straight to a specific clinician assigned to you.")

    care_tab, direct_tab = st.tabs(["Care Team Channel", "Direct Messages"])

    # Care Team Channel tab
    with care_tab:
        st.subheader("Care Team Channel")
        messages = chat_service.get_general_messages(hospital_id, user.username)
        clear_general = st.button("Clear Care Team Messages", key="patient_clear_general")
        if clear_general:
            chat_service.clear_general_messages(hospital_id, user.username)
            st.success("Care team messages cleared.")
            _rerun()
        _render_chat_messages(service, hospital_id, messages)

        # Form for sending a new message to the care team.
        with st.form("patient_general_chat_form", clear_on_submit=True):
            general_message = st.text_input(
                "Message the care team",
                placeholder="Type your message...",
                key="patient_general_message"
            )
            send_general = st.form_submit_button("Send")

        if send_general:
            text = (general_message or "").strip()
            if text:
                chat_service.add_general_message(
                    hospital_id,
                    user.username,
                    user.username,
                    user.role,
                    text
                )
                _rerun()

    # Direct Messages tab
    with direct_tab:
        st.subheader("Direct Messages With Assigned Clinicians")
        assigned_clinicians = service.get_assigned_clinicians_for_patient(hospital_id, user.username)

        if not assigned_clinicians:
            st.info("You don't have any clinicians assigned yet. Once assigned, you can chat with them here.")
        else:
            # Create a map of usernames to full names for the selectbox.
            clinician_map = {}
            for clinician_username in assigned_clinicians:
                clinician_data = service.get_user_by_username(hospital_id, clinician_username, 'clinician')
                full_name = clinician_data.get('full_name') if clinician_data else None
                clinician_map[clinician_username] = full_name or clinician_username

            selected_clinician = st.selectbox(
                "Select a clinician",
                assigned_clinicians,
                format_func=lambda username: clinician_map.get(username, username),
                key="patient_direct_chat_clinician"
            )

            if selected_clinician:
                messages = chat_service.get_direct_messages(hospital_id, user.username, selected_clinician)
                clear_direct = st.button("Clear Direct Messages", key=f"patient_clear_direct_{selected_clinician}")
                if clear_direct:
                    chat_service.clear_direct_messages(hospital_id, user.username, selected_clinician)
                    st.success("Direct conversation cleared.")
                    _rerun()
                _render_chat_messages(service, hospital_id, messages)

                # Form for sending a new direct message.
                prompt_name = clinician_map.get(selected_clinician, selected_clinician)
                form_key = f"patient_direct_chat_form_{selected_clinician}"
                input_key = f"patient_direct_message_{selected_clinician}"
                with st.form(form_key, clear_on_submit=True):
                    direct_message = st.text_input(
                        f"Message {prompt_name}",
                        placeholder="Write a private message...",
                        key=input_key
                    )
                    send_direct = st.form_submit_button("Send")

                if send_direct:
                    text = (direct_message or "").strip()
                    if text:
                        chat_service.add_direct_message(
                            hospital_id,
                            user.username,
                            selected_clinician,
                            user.username,
                            user.role,
                            text
                        )
                        _rerun()

    _schedule_auto_refresh(f"patient_chat_refresh_{user.username}", expected_page="patient_messaging")

def _render_clinician_chat_page(service, hospital_id):
    """Renders the clinician's secure messaging interface.

    Args:
        service: The main application service instance.
        hospital_id (str): The ID of the hospital.
    """
    st.markdown("<h2 style='text-align: center;'>Patient Messaging</h2>", unsafe_allow_html=True)
    chat_service = getattr(service, 'chat', None)
    if not chat_service:
        st.error("Chat service is currently unavailable.")
        return

    user = st.session_state.current_user
    patients = service.get_all_patients(hospital_id)
    if not patients:
        st.info("No patients assigned to you yet.")
        return

    # Create a map of patient usernames to full names for the selectbox.
    patient_map = {}
    for patient in patients:
        username = patient.get('username')
        full_name = patient.get('full_name')
        patient_map[username] = full_name or username

    patient_usernames = list(patient_map.keys())
    selected_patient = st.selectbox(
        "Select a patient",
        patient_usernames,
        format_func=lambda username: patient_map.get(username, username),
        key="clinician_chat_patient"
    )

    st.info("Respond in the care team channel to keep everyone informed, or send a direct note the patient sees immediately.")

    care_tab, direct_tab = st.tabs(["Care Team Channel", "Direct Message"])

    # Care Team Channel tab
    with care_tab:
        st.subheader("Care Team Channel")
        messages = chat_service.get_general_messages(hospital_id, selected_patient)
        clear_general = st.button("Clear Care Team Messages", key=f"clinician_clear_general_{selected_patient}")
        if clear_general:
            chat_service.clear_general_messages(hospital_id, selected_patient)
            st.success("Care team messages cleared.")
            _rerun()
        _render_chat_messages(service, hospital_id, messages)

        # Form for sending a new message to the care team.
        form_key = f"clinician_general_chat_form_{selected_patient}"
        input_key = f"clinician_general_message_{selected_patient}"
        with st.form(form_key, clear_on_submit=True):
            general_prompt = f"Message {patient_map.get(selected_patient, selected_patient)}'s care team"
            general_message = st.text_input(
                general_prompt,
                placeholder="Share an update with the care team...",
                key=input_key
            )
            send_general = st.form_submit_button("Send")

        if send_general:
            text = (general_message or "").strip()
            if text:
                chat_service.add_general_message(
                    hospital_id,
                    selected_patient,
                    user.username,
                    user.role,
                    text
                )
                _rerun()

    # Direct Message tab
    with direct_tab:
        st.subheader("Direct Message With Patient")
        messages = chat_service.get_direct_messages(hospital_id, selected_patient, user.username)
        clear_direct = st.button("Clear Direct Messages", key=f"clinician_clear_direct_{selected_patient}")
        if clear_direct:
            chat_service.clear_direct_messages(hospital_id, selected_patient, user.username)
            st.success("Direct conversation cleared.")
            _rerun()
        _render_chat_messages(service, hospital_id, messages)

        # Form for sending a new direct message.
        form_key = f"clinician_direct_chat_form_{selected_patient}"
        input_key = f"clinician_direct_message_{selected_patient}"
        with st.form(form_key, clear_on_submit=True):
            direct_prompt = f"Message {patient_map.get(selected_patient, selected_patient)}"
            direct_message = st.text_input(
                direct_prompt,
                placeholder="Write a private message...",
                key=input_key
            )
            send_direct = st.form_submit_button("Send")

        if send_direct:
            text = (direct_message or "").strip()
            if text:
                entry = chat_service.add_direct_message(
                    hospital_id,
                    selected_patient,
                    user.username,
                    user.username,
                    user.role,
                    text
                )
                if entry:
                    _rerun()
                else:
                    st.warning("You can only send direct messages to patients assigned to you.")

    refresh_key = f"clinician_chat_refresh_{user.username}_{selected_patient}"
    _schedule_auto_refresh(refresh_key, expected_page="clinician_messaging")

def _render_add_note_page(service, hospital_id):
    """Renders the page for a clinician to add a new note for a patient.

    Args:
        service: The main application service instance.
        hospital_id (str): The ID of the hospital.
    """
    st.markdown("<h2 style='text-align: center;'>Add a New Patient Note</h2>", unsafe_allow_html=True)
    patients = service.get_all_patients(hospital_id)
    if not patients:
        st.warning("No patients found for this hospital.")
        return
    patient_usernames = [p['username'] for p in patients]

    with st.form("add_note_form"):
        selected_patient = st.selectbox("Select Patient", patient_usernames)
        mood = st.slider("Mood (0-10)", 0, 10, 5)
        pain = st.slider("Pain (0-10)", 0, 10, 5)
        appetite = st.slider("Appetite (0-10)", 0, 10, 5)
        notes = st.text_area("Narrative Notes (patient stories, cultural needs, etc.)")
        diagnoses = st.text_area("Medical Notes and Diagnoses")
        share_with_patient = st.checkbox("Share this note with the patient", value=True,
                                         help="Uncheck to keep this note visible only to clinicians assigned to the patient.")
        submitted = st.form_submit_button("Save Note")
        if submitted:
            with st.spinner("Saving note..."):
                time.sleep(1)
                author_id = st.session_state.current_user.username
                note = PatientNote(
                    patient_id=selected_patient, author_id=author_id, mood=mood, pain=pain,
                    appetite=appetite, notes=notes, diagnoses=diagnoses, source="clinician", hospital_id=hospital_id,
                    hidden_from_patient=not share_with_patient
                )
                service.add_note(note, hospital_id)
                st.success(f"Note added successfully for patient '{selected_patient}'.")

def _render_add_patient_entry_page(service, hospital_id):
    """Renders the page for a patient to add a new personal health entry.

    Args:
        service: The main application service instance.
        hospital_id (str): The ID of the hospital.
    """
    st.markdown("<h2 style='text-align: center;'>Add a New Entry</h2>", unsafe_allow_html=True)

    # Display a persistent success message after saving an entry.
    if st.session_state.get('entry_saved_success'):
        st.success("Your entry has been saved successfully.")
        del st.session_state['entry_saved_success'] # Clear the flag to prevent re-showing.

    form = st.form("add_patient_entry_form")
    with form:
        mood = st.slider("My Mood (0-10)", 0, 10, 5)
        pain = st.slider("My Pain Level (0-10)", 0, 10, 5)
        appetite = st.slider("My Appetite (0-10)", 0, 10, 5)
        notes = st.text_area("How are you feeling today? Anything you want to share?")
        is_private = st.checkbox("Make this entry private (only you can see it)", value=False)
        submitted = st.form_submit_button("Save Entry")

    if submitted:
        with st.spinner("Saving entry..."):
            time.sleep(1)
            user = st.session_state.current_user
            note = PatientNote(
                patient_id=user.username, author_id=user.username, mood=mood, pain=pain,
                appetite=appetite, notes=notes, diagnoses="", source="patient", hospital_id=hospital_id, is_private=is_private
            )
            service.add_note(note, hospital_id)
            st.session_state.entry_saved_success = True
            st.rerun()

def _render_view_notes_page(service, hospital_id, patient_id=None):
    """Renders the page for viewing patient notes and entries.

    This page is used by both patients (to see their own notes) and clinicians
    (to see notes for a selected patient).

    Args:
        service: The main application service instance.
        hospital_id (str): The ID of the hospital.
        patient_id (str, optional): The ID of the patient whose notes are being viewed.
                                    If None, a selector is shown for clinicians.
    """
    user = st.session_state.current_user
    # Patient view
    if patient_id:
        st.markdown("<h2 style='text-align: center;'>My Medical Notes & Entries</h2>", unsafe_allow_html=True)
        notes = service.get_notes_for_patient(hospital_id, patient_id)
    # Clinician/Admin view
    else:
        st.markdown("<h2 style='text-align: center;'>View All Patient Notes & Entries</h2>", unsafe_allow_html=True)
        patients = service.get_all_patients(hospital_id)
        if not patients:
            st.warning("No patients assigned to you or no patients in this hospital.")
            return
        patient_usernames = [p['username'] for p in patients]
        selected_patient = st.selectbox("Select a patient to view their notes", patient_usernames)
        
        # Reset the profile view state if the selected patient changes.
        if st.session_state.get('viewing_profile_for_patient') and st.session_state.viewing_profile_for_patient != selected_patient:
            st.session_state.viewing_profile_for_patient = None

        # Clinicians can view the patient's profile.
        if user.role == 'clinician' and selected_patient:
            # Toggle button for viewing/hiding the patient profile.
            if st.session_state.get('viewing_profile_for_patient') != selected_patient:
                if st.button("View Patient Profile", key="view_patient_profile_btn"):
                    st.session_state.viewing_profile_for_patient = selected_patient
                    st.rerun()
            else:
                if st.button("Hide Patient Profile", key="hide_patient_profile_btn"):
                    st.session_state.viewing_profile_for_patient = None
                    st.rerun()
                patient_data = service.get_user_by_username(hospital_id, selected_patient, 'patient')
                _display_user_profile_details(patient_data)
            
            st.divider() # Add a divider for better separation
        # Clinicians can search within a patient's notes.
        if user.role == 'clinician':
            search_term = st.text_input("Search notes for this patient:")
            if search_term:
                notes = service.search_notes(hospital_id, selected_patient, search_term)
            else:
                notes = service.get_notes_for_patient(hospital_id, selected_patient)
        else:
            notes = service.get_notes_for_patient(hospital_id, selected_patient)


    if not notes:
        st.info("No notes or entries found for this patient.")
    else:
        # Display notes sorted by timestamp, newest first.
        for note in sorted(notes, key=lambda x: x.get('timestamp', ''), reverse=True):
            source = note.get("source", "clinician")
            timestamp_str = note.get('timestamp')
            timestamp = datetime.datetime.fromisoformat(timestamp_str).strftime('%Y-%m-%d %H:%M:%S') if timestamp_str else "Unknown Date"
            author = note.get('author_id', 'Unknown')

            privacy_icon = "🔒" if note.get('is_private') else ""
            hidden_from_patient = note.get('hidden_from_patient', False)

            # Determine the title and visibility of the note expander.
            if source == "patient":
                expander_title = f"Patient Entry from {timestamp} {privacy_icon}"
                if note.get('is_private') and user.role != 'patient':
                    st.write("This note is private and cannot be viewed.")
                    continue
            else:
                if hidden_from_patient and user.role == 'patient':
                    continue
                hidden_suffix = " [Clinicians Only]" if hidden_from_patient else ""
                expander_title = f"Clinical Note from {timestamp} (by {author}){hidden_suffix}"
            
            with st.expander(expander_title):
                # Display note details, using .get() to prevent errors if fields are missing.
                st.metric("Mood", f"{note.get('mood', 'N/A')}/10")
                st.metric("Pain", f"{note.get('pain', 'N/A')}/10")
                st.metric("Appetite", f"{note.get('appetite', 'N/A')}/10")
                st.write("**Patient wrote:**" if source == "patient" else "**Narrative Notes:**")
                st.write(note.get('notes') or "_No notes provided._")
                if source == "clinician":
                    st.write("**Diagnoses/Medical Notes:**")
                    st.write(note.get('diagnoses') or "_No diagnoses provided._")
                    if hidden_from_patient:
                        st.info("This note is hidden from the patient and is only visible to assigned clinicians.")
                
                # Display AI feedback if available and approved.
                ai_feedback = note.get('ai_feedback')
                if ai_feedback:
                    if ai_feedback.get('status') == 'approved':
                        st.divider()
                        st.markdown("**AI Generated Feedback**")
                        st.success(ai_feedback.get('text'))
                    elif ai_feedback.get('status') == 'pending':
                        st.divider()
                        st.info("Awaiting AI feedback approval from clinician to ensure your safety.")
                
                # Allow patients to request AI feedback on their non-private notes.
                elif user.role == 'patient' and note.get('source') == 'patient' and not note.get('is_private'):
                    st.divider()
                    if st.button("Generate AI Feedback", key=f"gen_ai_{note.get('note_id')}"):
                        with st.spinner("Generating AI Feedback..."):
                            success = service.generate_and_store_ai_feedback(note.get('note_id'), hospital_id)
                        if success:
                            st.success("AI feedback is being generated. A clinician will review it shortly.")
                            st.rerun()
                        else:
                            st.error("Could not generate feedback for this note.")

                
                # Determine if the current user can edit or delete the note.
                can_edit_or_delete = (user.role == 'patient' and note.get('source') == 'patient') or \
                                     (user.role == 'clinician' and note.get('source') == 'clinician' and note.get('author_id') == user.username)

                if can_edit_or_delete:
                    st.divider()
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("Edit Note", key=f"edit_{note.get('note_id', 'unknown_id')}"):
                            st.session_state.editing_note_id = note.get('note_id')
                            st.rerun()
                    with c2:
                        if st.button("Delete Note", key=f"delete_{note.get('note_id', 'unknown_id')}"):
                            service.delete_note(note['note_id'], hospital_id)
                            st.success("Note deleted successfully.")
                            st.rerun()

                # If editing, display the note editing form.
                if st.session_state.get('editing_note_id') == note.get('note_id'):
                    with st.form(key=f"edit_form_{note.get('note_id')}"):
                        st.subheader("Edit Note")
                        edited_notes = st.text_area("Notes", value=note.get('notes', ''))
                        edited_diagnoses = st.text_area("Diagnoses", value=note.get('diagnoses', '')) if source == "clinician" else None
                        share_checkbox = None
                        if source == "clinician":
                            share_checkbox = st.checkbox(
                                "Share with patient",
                                value=not hidden_from_patient,
                                help="Uncheck to keep this note visible only to clinicians assigned to the patient."
                            )
                        
                        save_changes = st.form_submit_button("Save Changes")
                        if save_changes:
                            updated_data = {'notes': edited_notes}
                            if edited_diagnoses is not None:
                                updated_data['diagnoses'] = edited_diagnoses
                                updated_data['hidden_from_patient'] = not share_checkbox
                            elif source == "clinician" and share_checkbox is not None:
                                updated_data['hidden_from_patient'] = not share_checkbox
                            service.update_note(hospital_id, note.get('note_id'), updated_data)
                            st.session_state.editing_note_id = None
                            st.success("Note updated.")
                            st.rerun()

def _render_user_management_entry(user_key, user_data, service, hospital_id):
    """Renders a single user entry in the admin management panel with action buttons.

    Args:
        user_key (str): A unique key identifying the user.
        user_data (dict): The user's data.
        service: The main application service instance.
        hospital_id (str): The ID of the hospital.
    """
    _display_user_profile_details(user_data)
    
    is_pending = user_data.get('status') == 'pending'
    
    st.divider() # Add a divider for better separation.
    
    # Action buttons (Approve, Edit, Delete).
    num_cols = 3 if is_pending else 2
    cols = st.columns(num_cols)
    
    if is_pending:
        if cols[0].button("Approve User", key=f"approve_{user_key}", type="primary"):
            service.approve_user(user_data.get('username'), user_data.get('role'), hospital_id)
            st.success(f"User {user_data.get('username')} approved.")
            st.rerun()

    if cols[num_cols-2].button("Edit User", key=f"edit_{user_key}"):
        st.session_state.editing_user_key = user_key
        st.rerun()

    current_admin_user = st.session_state.current_user
    is_self = (current_admin_user.username == user_data.get('username') and current_admin_user.role == user_data.get('role'))
    if cols[num_cols-1].button("Delete User", key=f"delete_{user_key}", disabled=is_self, type="secondary"):
        if service.delete_user(hospital_id, user_data.get('username'), user_data.get('role')):
            st.success(f"User {user_data.get('username')} deleted successfully.")
            st.rerun()
        else:
            st.error("Failed to delete user.")

    # If this user is being edited, show the edit form.
    if st.session_state.get('editing_user_key') == user_key:
        with st.form(key=f"edit_form_{user_key}"):
            st.subheader(f"Editing {user_data.get('username')}")
            full_name = st.text_input("Full Name", value=user_data.get('full_name', ''))
            dob_val = user_data.get('dob')
            dob = st.date_input("Date of Birth", value=datetime.date.fromisoformat(dob_val) if dob_val else None, min_value=datetime.date(1900, 1, 1))
            sex_options = ["Male", "Female", "Intersex", "Prefer not to say"]
            sex = st.selectbox("Sex", options=sex_options, index=sex_options.index(user_data.get('sex')) if user_data.get('sex') in sex_options else 0)
            pronouns = st.text_input("Pronouns", value=user_data.get('pronouns', ''))
            bio = st.text_area("Bio", value=user_data.get('bio', ''))
            
            save_changes = st.form_submit_button("Save Changes")
            if save_changes:
                update_details = {
                    "full_name": full_name, "dob": dob.isoformat() if dob else None, "sex": sex,
                    "pronouns": pronouns, "bio": bio
                }
                if service.update_user_profile(hospital_id, user_data.get('username'), user_data.get('role'), update_details):
                    st.success("Profile updated successfully!")
                    st.session_state.editing_user_key = None
                    st.rerun()
                else:
                    st.error("Failed to update profile.")

def _render_admin_page(service, hospital_id):
    """Renders the main admin panel for user management and data export.

    Args:
        service: The main application service instance.
        hospital_id (str): The ID of the hospital.
    """
    st.markdown(f"<h2 style='text-align: center;'>Admin Panel for {hospital_id}</h2>", unsafe_allow_html=True)
    st.subheader("User Accounts")
    users_dict = service.get_all_users(hospital_id)

    if not users_dict:
        st.info("No users found for this hospital.")
    else:
        # Separate users into pending and active for display.
        active_users = {k: v for k, v in users_dict.items() if v.get('status') == 'approved'}
        pending_users = {k: v for k, v in users_dict.items() if v.get('status') == 'pending'}

        if pending_users:
            st.markdown("##### Awaiting Approval")
            for user_key, user_data in sorted(pending_users.items()):
                with st.expander(f"**{user_data.get('username')}** ({user_data.get('role', '').capitalize()}) - ⏳ Pending"):
                    _render_user_management_entry(user_key, user_data, service, hospital_id)

        if active_users:
            st.markdown("##### Active Accounts")
            for user_key, user_data in sorted(active_users.items()):
                with st.expander(f"**{user_data.get('username')}** ({user_data.get('role', '').capitalize()})"):
                    _render_user_management_entry(user_key, user_data, service, hospital_id)

    st.divider() # Add a divider for better separation.
    
    # Form for admins to create new users directly.
    st.markdown("##### Create a New User")
    with st.expander("Create a New User"):
        with st.form("create_user_form"):
            st.subheader("New User Details")
            new_full_name = st.text_input("Full Name")
            new_role = st.selectbox("Role", ["patient", "clinician", "admin"])
            new_username = st.text_input("Username")
            new_password = st.text_input("Password", type="password")
            
            st.markdown("---")
            new_dob = st.date_input("Date of Birth", min_value=datetime.date(1900, 1, 1), key="new_dob")
            new_sex = st.selectbox("Sex", ["Male", "Female", "Intersex", "Prefer not to say"], key="new_sex")
            new_pronouns = st.text_input("Pronouns (e.g., she/her, they/them)", key="new_pronouns")
            new_bio = st.text_area("Bio (Optional)", key="new_bio")

            create_submitted = st.form_submit_button("Create User")
            if create_submitted:
                if not new_username or not new_password or not new_full_name:
                    st.error("Full Name, Username, and Password are required.")
                else:
                    result = service.register_user(new_username, new_password, new_role, hospital_id, new_full_name, new_dob.isoformat(), new_sex, new_pronouns, new_bio)
                    if result is True or result == 'pending':
                        st.success(f"User '{new_username}' created successfully!")
                        st.rerun()
                    else:
                        st.error(f"A profile for username '{new_username}' with the role '{new_role}' may already exist.")

    st.divider() # Add a divider for better separation.

    # Data export section.
    st.header("Data Export")
    st.warning(f"The following exports contain data for **{hospital_id} ONLY**.")
    hospital_data = service.get_hospital_dataset(hospital_id)

    # Export as raw JSON.
    st.subheader("1. Export as Raw JSON")
    json_string = json.dumps(hospital_data, indent=4)
    st.download_button(
       "Download Hospital Data (JSON)", json_string,
       f"carelog_{hospital_id}_export_{datetime.date.today()}.json", "application/json"
    )
    st.divider() # Add a divider for better separation.

    # Export as CSV files.
    st.subheader("2. Export as CSV")
    col1, col2 = st.columns(2)
    with col1:
        users_dict_export = hospital_data.get('users', {})
        if users_dict_export:
            # Prepare user data for export, excluding sensitive fields.
            export_users_data = []
            for user_key, u_data in users_dict_export.items():
                user_export_data = {
                    'username': u_data.get('username'),
                    'role': u_data.get('role'),
                    'status': u_data.get('status'),
                    'full_name': u_data.get('full_name'),
                    'dob': u_data.get('dob'),
                    'sex': u_data.get('sex'),
                    'pronouns': u_data.get('pronouns'),
                    'bio': u_data.get('bio'),
                    'assigned_clinicians': ', '.join(u_data.get('assigned_clinicians', [])) if u_data.get('role') == 'patient' else ''
                }
                export_users_data.append(user_export_data)
            users_df = pd.DataFrame(export_users_data)
            st.download_button(
                "Download Users (CSV)", users_df.to_csv(index=False).encode('utf-8'),
                f"carelog_{hospital_id}_users_{datetime.date.today()}.csv", "text/csv"
            )
    with col2:
        notes_list = hospital_data.get('notes', [])
        if notes_list:
            notes_df = pd.DataFrame(notes_list)
            desired_columns = ['timestamp', 'patient_id', 'author_id', 'source', 'mood', 'pain', 'appetite', 'notes', 'diagnoses']
            # Ensure all desired columns exist before exporting.
            for col in desired_columns:
                if col not in notes_df.columns: notes_df[col] = None
            st.download_button(
                "Download Notes (CSV)", notes_df[desired_columns].to_csv(index=False).encode('utf-8'),
                f"carelog_{hospital_id}_notes_{datetime.date.today()}.csv", "text/csv"
            )
    st.divider() # Add a divider for better separation.

    # Export as a human-readable text report.
    st.subheader("3. Export as Human-Readable Report")
    st.write("Download all notes as a simple, formatted text file for easy reading or printing.")
    notes_list = hospital_data.get('notes', [])
    if not notes_list:
        st.info("There are no notes to export in this report.")
    else:
        report_content = [f"CareLog Notes Report - Generated on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n", "="*80 + "\n"]
        for note in sorted(notes_list, key=lambda x: x.get('timestamp', '')):
            timestamp_str = note.get('timestamp')
            timestamp = datetime.datetime.fromisoformat(timestamp_str).strftime('%Y-%m-%d %H:%M:%S') if timestamp_str else "Unknown Date"
            report_content.extend([
                f"Timestamp: {timestamp}",
                f"Patient ID: {note.get('patient_id', 'N/A')}",
                f"Author ID: {note.get('author_id', 'N/A')}",
                f"Entry Source: {note.get('source', 'clinician').capitalize()}",
                f"Mood: {note.get('mood', 'N/A')}/10 | Pain: {note.get('pain', 'N/A')}/10 | Appetite: {note.get('appetite', 'N/A')}/10",
                "\nPatient Wrote:\n" + "-"*15 if note.get('source') == 'patient' else "\nNarrative Notes:\n" + "-"*18,
                note.get('notes', 'N/A') or "N/A"
            ])
            if note.get('source', 'clinician') == 'clinician':
                report_content.extend(["\nDiagnoses/Medical Notes:\n" + "-"*25, note.get('diagnoses', 'N/A') or "N/A"])
            
            ai_feedback = note.get('ai_feedback')
            if ai_feedback and ai_feedback.get('status') == 'approved':
                report_content.extend([
                    "\n\nAI Generated Feedback:\n" + "-"*22,
                    ai_feedback.get('text', 'N/A')
                ])
            report_content.append("\n" + "="*80 + "\n")
        
        final_report = "\n".join(report_content)
        st.download_button(
            label="Download Notes Report (.txt)", data=final_report.encode('utf-8'),
            file_name=f"carelog_report_notes_{datetime.date.today()}.txt", mime="text/plain"
        )

def _render_review_feedback_page(service, hospital_id):
    """Renders the page for clinicians to review and approve AI-generated feedback.

    Args:
        service: The main application service instance.
        hospital_id (str): The ID of the hospital.
    """
    st.markdown("<h2 style='text-align: center;'>Review AI Feedback</h2>", unsafe_allow_html=True)
    pending_feedback = service.get_pending_feedback(hospital_id)

    if not pending_feedback:
        st.info("No AI feedback to review.")
        return

    for note in pending_feedback:
        patient_id_display = note.get('patient_id', 'Unknown Patient')
        timestamp_str = note.get('timestamp')
        timestamp_display = datetime.datetime.fromisoformat(timestamp_str).strftime('%Y-%m-%d %H:%M:%S') if timestamp_str else "Unknown Date"
        notes_display = note.get('notes', '_No notes provided._')

        st.subheader(f"Feedback for {patient_id_display}'s note from {timestamp_display}")
        st.write("**Patient's Note:**")
        st.write(notes_display)
        
        # Allow the clinician to edit the AI feedback before approval.
        edited_feedback = st.text_area(
            "**AI Generated Feedback (Edit if necessary):**",
            value=note.get('ai_feedback', {}).get('text', 'N/A'),
            height=200,
            key=f"edit_feedback_{note.get('note_id', 'unknown_id')}"
        )

        # Approve/Reject buttons.
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Approve Feedback", key=f"approve_{note.get('note_id', 'unknown_id')}", use_container_width=True, type="primary"):
                service.approve_ai_feedback(note.get('note_id'), hospital_id, edited_feedback)
                st.success("Feedback approved!")
                st.rerun()
        with col2:
            if st.button("Reject Feedback", key=f"reject_{note.get('note_id', 'unknown_id')}", use_container_width=True):
                service.reject_ai_feedback(note.get('note_id'), hospital_id)
                st.success("Feedback has been rejected and removed.")
                st.rerun()

def _render_assign_clinicians_page(service, hospital_id):
    """Renders the admin page for assigning clinicians to patients.

    Args:
        service: The main application service instance.
        hospital_id (str): The ID of the hospital.
    """
    st.markdown("<h2 style='text-align: center;'>Assign Clinicians to Patients</h2>", unsafe_allow_html=True)

    patients = service.get_all_patients(hospital_id)
    clinicians = service.get_all_clinicians(hospital_id)

    if not patients or not clinicians:
        st.warning("You need at least one approved patient and one approved clinician to make assignments.")
        return

    patient_usernames = [p['username'] for p in patients]
    selected_patient_username = st.selectbox("Select a Patient", patient_usernames)

    if selected_patient_username:
        patient_user_key = f"{selected_patient_username}_patient"
        all_users = service.get_all_users(hospital_id)
        patient_data = all_users.get(patient_user_key, {})
        assigned_clinicians = patient_data.get('assigned_clinicians', [])

        st.write(f"**Assigned Clinicians for {selected_patient_username}:**")
        if not assigned_clinicians:
            st.info("No clinicians assigned.")
        else:
            # List currently assigned clinicians with an "Unassign" button for each.
            for clin in assigned_clinicians:
                col1, col2 = st.columns([4, 1])
                col1.write(clin)
                if col2.button("Unassign", key=f"unassign_{clin}_{selected_patient_username}"):
                    service.unassign_clinician_from_patient(hospital_id, selected_patient_username, clin)
                    st.success(f"Unassigned {clin} from {selected_patient_username}.")
                    st.rerun()

        st.divider() # Add a divider for better separation.
        st.subheader("Assign a New Clinician")
        # Show only clinicians who are not already assigned to this patient.
        available_clinicians = [c['username'] for c in clinicians if c['username'] not in assigned_clinicians]
        if not available_clinicians:
            st.write("All available clinicians are already assigned to this patient.")
        else:
            selected_clinician = st.selectbox("Select Clinician to Assign", available_clinicians)
            if st.button("Assign Clinician"):
                service.assign_clinician_to_patient(hospital_id, selected_patient_username, selected_clinician)
                st.success(f"Assigned {selected_clinician} to {selected_patient_username}.")
                st.rerun()

def _render_pain_alerts_page(service, hospital_id):
    """Renders the page for clinicians to view and dismiss high-pain alerts.

    Args:
        service: The main application service instance.
        hospital_id (str): The ID of the hospital.
    """
    st.markdown("<h2 style='text-align: center;'>Patient Pain Alerts</h2>", unsafe_allow_html=True)
    st.info("This page lists entries where patients have reported a pain level of 10/10.")
    alerts = service.get_pain_alerts(hospital_id)

    if not alerts:
        st.success("No active pain alerts. Great!")
        return

    # Display alerts sorted by timestamp, newest first.
    for alert in sorted(alerts, key=lambda x: x.get('timestamp', ''), reverse=True):
        timestamp_str = alert.get('timestamp')
        timestamp = datetime.datetime.fromisoformat(timestamp_str).strftime('%Y-%m-%d %H:%M') if timestamp_str else "Unknown"
        st.error(f"**Patient:** {alert.get('patient_id')} at **{timestamp}** reported extreme pain (10/10).")
        if st.button("Acknowledge & Dismiss", key=f"dismiss_{alert.get('alert_id')}"):
            service.dismiss_alert(hospital_id, alert.get('alert_id'))
            st.success("Alert dismissed.")
            st.rerun()