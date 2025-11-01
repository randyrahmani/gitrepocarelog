"""
UI tests for the CareLog application using Streamlit's AppTest framework.

These tests simulate user interactions with the frontend to verify that the
GUI behaves as expected. They cover component rendering, button clicks,
form submissions, and session state changes.
"""
import hashlib
from streamlit.testing.v1 import AppTest

from modules.models import User


def test_ui_welcome_page_buttons():
    """
    Tests the navigation buttons on the welcome page.

    Verifies that clicking the 'Login' and 'Register' buttons correctly
    updates the `auth_page` session state to navigate to the respective forms.
    """
    def render():
        import gui as gui_module

        gui_module.show_welcome_page()

    app = AppTest.from_function(render, default_timeout=15)
    app.session_state["auth_page"] = "welcome"
    app.run()
    assert any("Welcome to CareLog" in md.value for md in app.markdown)

    app.button[0].click().run()
    assert app.session_state["auth_page"] == "login"

    app.session_state["auth_page"] = "welcome"
    app.button[1].click().run()
    assert app.session_state["auth_page"] == "register"


def test_ui_registration_validation(monkeypatch, service):
    """
    Tests the input validation on the registration form.

    Verifies that submitting the form with a weak password displays the
    appropriate error message to the user.
    """
    monkeypatch.setattr("time.sleep", lambda *_: None)

    def render(svc):
        import gui as gui_module

        gui_module.show_register_form(svc)

    app = AppTest.from_function(render, args=(service,), default_timeout=15)
    app.run()

    text_inputs = app.text_input
    text_inputs[0].input("Test User")
    text_inputs[1].input("TESTHOSP")
    text_inputs[2].input("tester")
    text_inputs[3].input("weak")
    buttons = {btn.label: btn for btn in app.button}
    buttons["Register"].click().run()

    assert any("Password must be at least 8 characters" in err.value for err in app.error)


def test_ui_login_pending_message(monkeypatch, service):
    """
    Tests the login behavior for a user whose account is pending approval.

    Verifies that when a 'pending' user attempts to log in, a warning
    message is displayed.
    """
    monkeypatch.setattr("time.sleep", lambda *_: None)
    hospital_id = "UIHOSP"
    salt = "salt_pending_clinician"
    password = "V4lid!Pass"
    password_hash = hashlib.sha256((salt + password).encode()).hexdigest()
    service._data["hospitals"][hospital_id] = {
        "users": {
            "pending_clinician": {
                "username": "pending",
                "password_hash": password_hash,
                "salt": salt,
                "role": "clinician",
                "status": "pending",
                "full_name": "Pending Clinician",
                "dob": "1990-01-01",
                "sex": "F",
                "pronouns": "she/her",
                "bio": "",
                "assigned_clinicians": [],
            }
        },
        "notes": [],
        "alerts": [],
        "chats": {"general": {}, "direct": {}},
    }

    def render(svc):
        import gui as gui_module

        gui_module.show_login_form(svc)

    app = AppTest.from_function(render, args=(service,), default_timeout=15)
    app.session_state["auth_page"] = "login"
    app.run()

    text_inputs = app.text_input
    text_inputs[0].input(hospital_id)
    text_inputs[1].input("pending")
    text_inputs[2].input("V4lid!Pass")
    app.selectbox[0].select("clinician")
    buttons = {btn.label: btn for btn in app.button}
    buttons["Login"].click().run()

    assert any("pending approval" in warn.value for warn in app.warning)


def test_ui_main_dashboard_render(service):
    """
    Tests that the main application dashboard renders correctly for a logged-in admin.

    Verifies that after login, the admin user is shown the correct dashboard view.
    """
    hospital_id = "UIAPP"
    service._data["hospitals"][hospital_id] = {
        "users": {
            "admin_admin": {
                "username": "admin",
                "password_hash": "",
                "salt": "",
                "role": "admin",
                "status": "approved",
                "full_name": "Admin",
                "dob": "1980-01-01",
                "sex": "F",
                "pronouns": "she/her",
                "bio": "Admin user",
                "assigned_clinicians": [],
            }
        },
        "notes": [],
        "alerts": [],
        "chats": {"general": {}, "direct": {}},
    }

    def render(svc, user, hospital):
        import gui as gui_module
        import streamlit as st

        st.session_state["current_user"] = user
        st.session_state["hospital_id"] = hospital
        gui_module.show_main_app(svc)

    user = User("admin", "", "admin", "Admin", "1980-01-01", "F", "she/her", "Admin user")
    app = AppTest.from_function(render, args=(service, user, hospital_id), default_timeout=15)
    app.run()

    markdown_values = [md.value for md in app.markdown]
    assert any("Admin Console" in value for value in markdown_values)
