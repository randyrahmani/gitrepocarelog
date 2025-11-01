"""
This is the main entry point for the CareLog Streamlit application.

This script handles the following key responsibilities:
- Sets the overall page configuration for the Streamlit app.
- Initializes the main `CareLogService`, which manages all backend logic and data.
- Manages the session state to track the current user, hospital, and authentication flow.
- Routes the user to the appropriate UI component (either the authentication pages or the main app)
  based on their login status.
"""
# carelog/main.py

import streamlit as st
from modules.auth import CareLogService
import gui

# Set the basic configuration for the Streamlit page.
st.set_page_config(
    page_title="CareLog",
    layout="wide"
)

# Service Initialization
@st.cache_resource
def get_carelog_service():
    """
    Initializes and returns the main CareLogService instance.

    This function is decorated with `@st.cache_resource` to ensure that the
    service is created only once per session, preserving its state across
    app reruns.

    Returns:
        CareLogService: The singleton instance of the main application service.
    """
    return CareLogService()

# Get the singleton service instance.
service = get_carelog_service()

# Session State Management
# Initialize session state variables if they don't already exist.
# This ensures that the app has a consistent state to work with.
if 'current_user' not in st.session_state:
    st.session_state.current_user = None
if 'hospital_id' not in st.session_state:
    st.session_state.hospital_id = None
if 'auth_page' not in st.session_state:
    st.session_state.auth_page = 'welcome'

# Main App Router
# This is the core logic that determines what the user sees.
if st.session_state.current_user and st.session_state.hospital_id:
    # If a user is logged in and a hospital context is set, show the main application UI.
    gui.show_main_app(service)
else:
    # If the user is not logged in, route them to the appropriate authentication page.
    # This allows for a multi-step login/registration process.
    if st.session_state.auth_page == 'welcome':
        gui.show_welcome_page()
    elif st.session_state.auth_page == 'login':
        gui.show_login_form(service)
    elif st.session_state.auth_page == 'register':
        gui.show_register_form(service)
