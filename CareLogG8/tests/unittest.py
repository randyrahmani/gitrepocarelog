"""
Unit tests for the CareLog application.

These tests focus on verifying the functionality of individual functions and methods
in isolation. They use mocking and fixtures to test specific logic within each
module, such as `auth`, `chat`, `encryption`, `gemini`, and `gui`.
"""
import hashlib
from datetime import datetime, timedelta, timezone
import types
from pathlib import Path

import pytest

from modules import auth as auth_module
from modules import chat as chat_module
from modules import encryption as encryption_module
from modules import gemini as gemini_module
import gui as gui_module
from modules.models import PatientNote, User


STRONG_PASSWORD = "V4lid!Pass"


def _make_user_record(username, role, password="V4lid!Pass", status="approved", **extra):
    """
    Helper function to create a user data dictionary for testing purposes.

    This simplifies the creation of user records by handling password hashing
    and providing sensible defaults for common fields.

    Args:
        username (str): The user's username.
        role (str): The user's role (e.g., 'patient', 'clinician').
        password (str, optional): The user's plaintext password. Defaults to STRONG_PASSWORD.
        status (str, optional): The user's account status. Defaults to "approved".
        **extra: Additional key-value pairs to include in the user record.

    Returns:
        dict: A dictionary representing a user record.
    """
    salt = f"salt_{username}_{role}"
    password_hash = hashlib.sha256((salt + password).encode()).hexdigest()
    record = {
        "username": username,
        "password_hash": password_hash,
        "salt": salt,
        "role": role,
        "status": status,
        "full_name": f"{username.title()} Name",
        "dob": "1990-01-01",
        "sex": "Other",
        "pronouns": "they/them",
        "bio": "bio",
        "assigned_clinicians": extra.get("assigned_clinicians", []),
    }
    record.update(extra)
    return record


def test_is_strong_password_variations(service):
    """
    Tests the password strength validation logic with various inputs.

    Verifies that the `_is_strong_password` method correctly identifies both weak and strong passwords.
    """
    assert not service._is_strong_password("short1!")
    assert not service._is_strong_password("alllowercase1!")
    assert not service._is_strong_password("ALLUPPERCASE1!")
    assert not service._is_strong_password("NoDigits!!")
    assert not service._is_strong_password("NoSpecial1")
    assert service._is_strong_password(STRONG_PASSWORD)


def test_register_user_new_hospital_admin_creates_dataset(service):
    """
    Verifies that registering the first admin for a new hospital correctly initializes the hospital's data structure.

    The first admin should be automatically approved, and the hospital should have empty lists for notes, alerts, and chat structures.
    """
    result = service.register_user(
        username="admin1",
        password=STRONG_PASSWORD,
        role="admin",
        hospital_id="HOSP1",
        full_name="Admin One",
        dob="1980-05-05",
        sex="F",
        pronouns="she/her",
        bio="Admin account",
    )
    assert result is True
    hospitals = service._data["hospitals"]
    assert "HOSP1" in hospitals
    admin = hospitals["HOSP1"]["users"]["admin1_admin"]
    assert admin["status"] == "approved"
    assert admin["assigned_clinicians"] == []
    assert hospitals["HOSP1"]["notes"] == []
    assert hospitals["HOSP1"]["alerts"] == []
    assert set(hospitals["HOSP1"]["chats"]) == {"general", "direct"}


def test_register_user_rejects_weak_password(service):
    """
    Tests that user registration fails if a weak password is provided.

    The service should return 'weak_password' and not create the user.
    """
    result = service.register_user(
        username="patient",
        password="weak",
        role="patient",
        hospital_id="HOSP1",
        full_name="Patient One",
        dob="1995-01-01",
        sex="M",
        pronouns="he/him",
        bio="Patient",
    )
    assert result == "weak_password"


def test_register_user_requires_admin_for_new_hospital(service):
    """
    Tests that a non-admin user cannot create a new hospital.

    Only an 'admin' role can register and create a new hospital ID. Other roles should be rejected if the hospital does not exist.
    """
    result = service.register_user(
        username="pat",
        password=STRONG_PASSWORD,
        role="patient",
        hospital_id="NEW_HOSP",
        full_name="Pat",
        dob="2000-01-01",
        sex="F",
        pronouns="she/her",
        bio="bio",
    )
    assert result == "hospital_not_found"


def test_register_user_existing_hospital_clinician_pending(hospital_service):
    """
    Tests that new clinicians or admins registering for an existing hospital are set to 'pending' status.

    Their accounts must be approved by an existing admin before they can log in.
    """
    service, hospital_id = hospital_service
    service.register_user(
        "admin",
        STRONG_PASSWORD,
        "admin",
        hospital_id,
        "Admin",
        "1980-01-01",
        "F",
        "she/her",
        "Admin",
    )
    result = service.register_user(
        "clin",
        STRONG_PASSWORD,
        "clinician",
        hospital_id,
        "Clinician",
        "1985-01-01",
        "M",
        "he/him",
        "Clin bio",
    )
    assert result == "pending"
    clinician = service._data["hospitals"][hospital_id]["users"]["clin_clinician"]
    assert clinician["status"] == "pending"


def test_register_user_duplicate_rejected(hospital_service):
    """
    Tests that registering a user with a username and role that already exists is rejected.

    The combination of username, role, and hospital must be unique.
    """
    service, hospital_id = hospital_service
    service._data["hospitals"][hospital_id]["users"]["dup_patient"] = _make_user_record("dup", "patient")
    result = service.register_user(
        "dup",
        STRONG_PASSWORD,
        "patient",
        hospital_id,
        "Dup User",
        "1999-09-09",
        "X",
        "they/them",
        "bio",
    )
    assert result is False


def test_login_success_and_logout(hospital_service):
    """
    Tests the full login and logout flow for a valid, approved user.

    Verifies that a successful login returns a User object and sets `current_user`, and that logout clears it.
    """
    service, hospital_id = hospital_service
    record = _make_user_record("user1", "patient")
    service._data["hospitals"][hospital_id]["users"]["user1_patient"] = record
    user = service.login("user1", STRONG_PASSWORD, "patient", hospital_id)
    assert isinstance(user, User)
    assert service.current_user.username == "user1"
    service.logout()
    assert service.current_user is None


def test_login_pending_user(hospital_service):
    """
    Tests that a user with a 'pending' status cannot log in.

    The login method should return the string 'pending' to indicate the account status.
    """
    service, hospital_id = hospital_service
    record = _make_user_record("user2", "clinician", status="pending")
    service._data["hospitals"][hospital_id]["users"]["user2_clinician"] = record
    result = service.login("user2", STRONG_PASSWORD, "clinician", hospital_id)
    assert result == "pending"


def test_login_wrong_password_returns_none(hospital_service):
    """
    Tests that a login attempt with an incorrect password fails.

    The login method should return `None` for invalid credentials.
    """
    service, hospital_id = hospital_service
    record = _make_user_record("user3", "patient")
    service._data["hospitals"][hospital_id]["users"]["user3_patient"] = record
    result = service.login("user3", "Wrong1!", "patient", hospital_id)
    assert result is None


def test_login_missing_salt_returns_error(hospital_service):
    """
    Tests that a login attempt for a user record missing a 'salt' field returns an error.

    This is a data integrity check; a missing salt indicates a corrupted user record.
    """
    service, hospital_id = hospital_service
    record = _make_user_record("user4", "patient")
    record.pop("salt")
    service._data["hospitals"][hospital_id]["users"]["user4_patient"] = record
    result = service.login("user4", STRONG_PASSWORD, "patient", hospital_id)
    assert result == "error"


def test_load_and_save_round_trip(service):
    """
    Tests that data saved by one service instance can be loaded correctly by another.

    This verifies the persistence layer (`_save_data` and `_load_data`).
    """
    hospital_id = "HOSP"
    service._data["hospitals"][hospital_id] = {
        "users": {"user_patient": _make_user_record("user", "patient")},
        "notes": [],
        "alerts": [],
        "chats": {"general": {}, "direct": {}},
    }
    service._save_data()

    new_service = auth_module.CareLogService()
    assert hospital_id in new_service._data["hospitals"]
    assert "user_patient" in new_service._data["hospitals"][hospital_id]["users"]


def test_load_invalid_data_starts_fresh(monkeypatch, tmp_path, dummy_encryptor):
    """
    Tests that if the data file is corrupted or invalid, the service initializes with a fresh, empty state.

    This ensures the application can recover from data file corruption without crashing.
    """
    data_file = tmp_path / "bad.json"
    data_file.write_text("invalid-data", encoding="utf-8")
    monkeypatch.setattr(auth_module, "DATA_FILE", str(data_file), raising=False)
    monkeypatch.setattr(auth_module, "encryptor", dummy_encryptor, raising=False)
    fresh_service = auth_module.CareLogService()
    assert fresh_service._data == {"hospitals": {}}


def test_ensure_hospital_defaults_adds_missing_sections(service):
    """
    Tests that the service correctly adds missing default data structures to a hospital's data.

    This is important for backward compatibility when new features (like 'alerts' or 'chats') are added.
    """
    service._data = {
        "hospitals": {
            "H1": {
                "users": {},
            }
        }
    }
    service._ensure_hospital_defaults()
    hospital = service._data["hospitals"]["H1"]
    assert hospital["notes"] == []
    assert hospital["alerts"] == []
    assert set(hospital["chats"]) == {"general", "direct"}


def test_add_note_creates_alert_for_severe_pain(hospital_service):
    """
    Tests that adding a patient note with a pain level of 10 correctly creates a pain alert.

    This verifies the critical alerting mechanism.
    """
    service, hospital_id = hospital_service
    note = PatientNote(
        patient_id="patient1",
        author_id="patient1",
        mood=5,
        pain=10,
        appetite=4,
        notes="Very high pain",
        diagnoses="",
        source="patient",
        hospital_id=hospital_id,
    )
    service.add_note(note, hospital_id)
    stored_note = service._data["hospitals"][hospital_id]["notes"][0]
    assert stored_note["notes"] == "Very high pain"
    alerts = service.get_pain_alerts(hospital_id)
    assert len(alerts) == 1
    assert alerts[0]["patient_id"] == "patient1"


def test_add_note_no_hospital_does_not_fail(service):
    """
    Tests that attempting to add a note for a non-existent hospital does not cause the application to crash.

    The service should handle this gracefully without modifying its data state.
    """
    note = PatientNote(
        patient_id="p1",
        author_id="p1",
        mood=1,
        pain=1,
        appetite=1,
        notes="",
        diagnoses="",
        source="patient",
        hospital_id="missing",
    )
    service.add_note(note, "missing")
    assert service._data == {"hospitals": {}}


def test_generate_and_store_ai_feedback_success(monkeypatch, hospital_service):
    """
    Tests the successful generation and storage of AI feedback for a note.

    Verifies that after generation, the feedback is stored on the note with a 'pending' status.
    """
    service, hospital_id = hospital_service
    note = PatientNote(
        patient_id="p1",
        author_id="clin1",
        mood=4,
        pain=6,
        appetite=3,
        notes="Needs feedback",
        diagnoses="flu",
        source="clinician",
        hospital_id=hospital_id,
    )
    service.add_note(note, hospital_id)

    def fake_feedback(notes, mood, pain, appetite):
        return f"Feedback for {notes}"

    monkeypatch.setattr(auth_module, "generate_feedback", fake_feedback, raising=False)
    success = service.generate_and_store_ai_feedback(note.note_id, hospital_id)
    assert success is True
    stored_note = service._data["hospitals"][hospital_id]["notes"][0]
    assert stored_note["ai_feedback"]["status"] == "pending"
    assert "Feedback for" in stored_note["ai_feedback"]["text"]


def test_generate_and_store_ai_feedback_handles_failures(monkeypatch, hospital_service):
    """
    Tests that if the AI feedback generation fails (returns None), the system handles it gracefully.

    The method should return `False` and not add any feedback data to the note.
    """
    service, hospital_id = hospital_service
    note = PatientNote(
        patient_id="p2",
        author_id="clin1",
        mood=4,
        pain=6,
        appetite=3,
        notes="No feedback",
        diagnoses="flu",
        source="clinician",
        hospital_id=hospital_id,
    )
    service.add_note(note, hospital_id)
    monkeypatch.setattr(auth_module, "generate_feedback", lambda *args, **_: None, raising=False)
    success = service.generate_and_store_ai_feedback(note.note_id, hospital_id)
    assert success is False


def test_get_notes_for_patient_respects_role(hospital_service):
    """
    Tests the access control logic for retrieving patient notes.

    Verifies that users can only see notes according to their role and assignments (e.g., clinicians only see notes for assigned patients, and private patient notes are hidden from others).
    """
    service, hospital_id = hospital_service
    service._data["hospitals"][hospital_id]["users"]["patient1_patient"] = _make_user_record(
        "patient1", "patient", assigned_clinicians=["clin1"]
    )
    service._data["hospitals"][hospital_id]["users"]["clin1_clinician"] = _make_user_record(
        "clin1", "clinician", status="approved"
    )
    notes = [
        {
            "note_id": "n1",
            "patient_id": "patient1",
            "source": "patient",
            "is_private": True,
        },
        {
            "note_id": "n2",
            "patient_id": "patient1",
            "source": "clinician",
            "is_private": False,
        },
    ]
    service._data["hospitals"][hospital_id]["notes"] = notes

    # Admin sees all notes
    service.current_user = User("admin", "hash", "admin", "", "", "", "", "")
    all_notes = service.get_notes_for_patient(hospital_id, "patient1")
    assert {n["note_id"] for n in all_notes} == {"n1", "n2"}

    # Assigned clinician hides patient's private notes
    service.current_user = User("clin1", "hash", "clinician", "", "", "", "", "")
    visible_notes = service.get_notes_for_patient(hospital_id, "patient1")
    assert [n["note_id"] for n in visible_notes] == ["n2"]

    # Unassigned clinician sees nothing
    service.current_user = User("clin2", "hash", "clinician", "", "", "", "", "")
    hidden = service.get_notes_for_patient(hospital_id, "patient1")
    assert hidden == []


def test_get_pending_feedback_filters_by_role(hospital_service):
    """
    Tests that retrieving pending AI feedback is correctly filtered based on the user's role.

    Admins should see all pending feedback, while clinicians should only see feedback for their assigned patients.
    """
    service, hospital_id = hospital_service
    service._data["hospitals"][hospital_id]["users"]["patient1_patient"] = _make_user_record(
        "patient1", "patient", assigned_clinicians=["clin1"]
    )
    service._data["hospitals"][hospital_id]["notes"] = [
        {"note_id": "n1", "patient_id": "patient1", "ai_feedback": {"status": "pending"}},
        {"note_id": "n2", "patient_id": "patient2", "ai_feedback": {"status": "pending"}},
    ]

    # Admin sees both
    service.current_user = User("admin", "hash", "admin", "", "", "", "", "")
    admin_pending = service.get_pending_feedback(hospital_id)
    assert {n["note_id"] for n in admin_pending} == {"n1", "n2"}

    # Clinician sees only assigned patients
    service.current_user = User("clin1", "hash", "clinician", "", "", "", "", "")
    clinician_pending = service.get_pending_feedback(hospital_id)
    assert [n["note_id"] for n in clinician_pending] == ["n1"]

    # Clinician with no assignments sees nothing
    service.current_user = User("clinX", "hash", "clinician", "", "", "", "", "")
    assert service.get_pending_feedback(hospital_id) == []


def test_feedback_approval_and_rejection(hospital_service, monkeypatch):
    """
    Tests the workflow for approving and rejecting AI-generated feedback.

    Verifies that approving changes the status and text, while rejecting removes the feedback object entirely.
    """
    service, hospital_id = hospital_service
    note = {
        "note_id": "note1",
        "patient_id": "patient1",
        "ai_feedback": {"status": "pending", "text": "draft"},
    }
    service._data["hospitals"][hospital_id]["notes"] = [note]

    approved = service.approve_ai_feedback("note1", hospital_id, "final text")
    assert approved is True
    assert note["ai_feedback"]["status"] == "approved"
    assert note["ai_feedback"]["text"] == "final text"

    rejected = service.reject_ai_feedback("note1", hospital_id)
    assert rejected is True
    assert "ai_feedback" not in note

    # Non-existent note
    assert service.approve_ai_feedback("missing", hospital_id, "text") is False
    assert service.reject_ai_feedback("missing", hospital_id) is False


def test_delete_note(hospital_service):
    """
    Tests the functionality for deleting a patient note.

    Also verifies that attempting to delete a non-existent note is idempotent and does not fail.
    """
    service, hospital_id = hospital_service
    service._data["hospitals"][hospital_id]["notes"] = [
        {"note_id": "keep"},
        {"note_id": "remove"},
    ]
    assert service.delete_note("remove", hospital_id) is True
    remaining = service._data["hospitals"][hospital_id]["notes"]
    assert remaining == [{"note_id": "keep"}]
    assert service.delete_note("missing", hospital_id) is True  # idempotent when already removed


def test_get_all_patients_respects_assignments(hospital_service):
    """
    Tests that `get_all_patients` correctly filters the patient list for clinicians.

    Admins should see all patients, while clinicians should only see patients they are assigned to.
    """
    service, hospital_id = hospital_service
    service._data["hospitals"][hospital_id]["users"] = {
        "p1_patient": _make_user_record("p1", "patient", assigned_clinicians=["clin1"]),
        "p2_patient": _make_user_record("p2", "patient", assigned_clinicians=[]),
    }
    service.current_user = User("admin", "hash", "admin", "", "", "", "", "")
    all_patients = service.get_all_patients(hospital_id)
    assert {p["username"] for p in all_patients} == {"p1", "p2"}

    service.current_user = User("clin1", "hash", "clinician", "", "", "", "", "")
    assigned = service.get_all_patients(hospital_id)
    assert [p["username"] for p in assigned] == ["p1"]


def test_getters_return_expected_defaults(service):
    """
    Tests that various getter methods return sensible empty defaults when called with non-existent IDs.

    This prevents errors from propagating when dealing with missing data.
    """
    assert service.get_all_users("unknown") == {}
    assert service.get_user_by_username("unknown", "user", "patient") == {}
    dataset = service.get_hospital_dataset("missing")
    assert dataset["users"] == {}
    assert dataset["notes"] == []
    assert service.get_all_hospitals() == []


def test_user_approval_and_pending_lookup(hospital_service):
    """
    Tests the user approval workflow.

    Verifies that pending users can be retrieved and that the `approve_user` method correctly changes their status.
    """
    service, hospital_id = hospital_service
    pending = _make_user_record("clin", "clinician", status="pending")
    service._data["hospitals"][hospital_id]["users"]["clin_clinician"] = pending
    pending_list = service.get_pending_users(hospital_id, "clinician")
    assert pending_list == [pending]
    assert service.approve_user("clin", "clinician", hospital_id) is True
    assert pending["status"] == "approved"
    assert service.approve_user("missing", "clinician", hospital_id) is False


def test_update_user_profile_updates_password(hospital_service):
    """
    Tests that the `update_user_profile` method can correctly update a user's details, including their password.

    When a password is changed, the salt should also be regenerated.
    """
    service, hospital_id = hospital_service
    record = _make_user_record("user", "patient")
    service._data["hospitals"][hospital_id]["users"]["user_patient"] = record
    updated = {
        "full_name": "New Name",
        "bio": "Updated bio",
        "new_password": "Another1!",
    }
    assert service.update_user_profile(hospital_id, "user", "patient", updated) is True
    assert record["full_name"] == "New Name"
    assert record["bio"] == "Updated bio"
    assert record["salt"].startswith("salt_") is False  # changed salt should differ
    assert service.update_user_profile(hospital_id, "missing", "patient", {}) is False


def test_update_note_changes_fields(hospital_service):
    """
    Tests that the `update_note` method correctly modifies the fields of an existing note.

    Verifies that a note's content can be changed and that the update is persisted.
    """
    service, hospital_id = hospital_service
    service._data["hospitals"][hospital_id]["notes"] = [
        {"note_id": "n1", "notes": "old"},
    ]
    assert service.update_note(hospital_id, "n1", {"notes": "new"}) is True
    assert service._data["hospitals"][hospital_id]["notes"][0]["notes"] == "new"
    assert service.update_note(hospital_id, "missing", {"notes": "x"}) is False


def test_delete_user_patient_cleans_related_data(hospital_service):
    """
    Tests that deleting a patient user also cleans up all their associated data.

    This includes their notes, chat messages, and alerts.
    """
    service, hospital_id = hospital_service
    service._data["hospitals"][hospital_id] = {
        "users": {
            "patient_patient": _make_user_record("patient", "patient"),
            "admin_admin": _make_user_record("admin", "admin"),
        },
        "notes": [
            {"note_id": "n1", "patient_id": "patient"},
            {"note_id": "n2", "patient_id": "other"},
        ],
        "alerts": [],
        "chats": {
            "general": {"patient": [{"sender": "patient", "text": "hello"}]},
            "direct": {"patient": {"clin": [{"sender": "clin", "text": "msg"}]}},
        },
    }
    service.current_user = User("admin", "hash", "admin", "", "", "", "", "")
    assert service.delete_user(hospital_id, "patient", "patient") is True
    users = service._data["hospitals"][hospital_id]["users"]
    assert "patient_patient" not in users
    assert service._data["hospitals"][hospital_id]["notes"] == [{"note_id": "n2", "patient_id": "other"}]
    assert service._data["hospitals"][hospital_id]["chats"]["general"] == {}
    assert service._data["hospitals"][hospital_id]["chats"]["direct"] == {}


def test_delete_user_clinician_updates_assignments(hospital_service):
    """
    Tests that deleting a clinician user correctly cleans up related data.

    This includes removing them from any patient's `assigned_clinicians` list, deleting their notes, and removing their chat messages.
    """
    service, hospital_id = hospital_service
    service._data["hospitals"][hospital_id] = {
        "users": {
            "patient_patient": _make_user_record("patient", "patient", assigned_clinicians=["clin"]),
            "clin_clinician": _make_user_record("clin", "clinician"),
            "admin_admin": _make_user_record("admin", "admin"),
        },
        "notes": [
            {"note_id": "n1", "patient_id": "patient", "author_id": "clin", "source": "clinician"},
            {"note_id": "n2", "patient_id": "patient", "author_id": "admin", "source": "admin"},
        ],
        "alerts": [],
        "chats": {
            "general": {"patient": [{"sender": "clin", "text": "hi"}]},
            "direct": {"patient": {"clin": [{"sender": "clin", "text": "hi"}]}},
        },
    }
    service.current_user = User("admin", "hash", "admin", "", "", "", "", "")
    assert service.delete_user(hospital_id, "clin", "clinician") is True
    users = service._data["hospitals"][hospital_id]["users"]
    assert service._data["hospitals"][hospital_id]["notes"] == [
        {"note_id": "n2", "patient_id": "patient", "author_id": "admin", "source": "admin"}
    ]
    assert users["patient_patient"]["assigned_clinicians"] == []
    assert service._data["hospitals"][hospital_id]["chats"]["direct"]["patient"] == {}
    assert service._data["hospitals"][hospital_id]["chats"]["general"]["patient"] == []


def test_delete_user_admin_removes_messages(hospital_service):
    """
    Tests that when an admin is deleted, their messages are removed from chat threads.

    This ensures that deleted users' content is purged from conversations.
    """
    service, hospital_id = hospital_service
    service._data["hospitals"][hospital_id] = {
        "users": {
            "admin_admin": _make_user_record("admin", "admin"),
            "other_admin": _make_user_record("other", "admin"),
        },
        "notes": [],
        "alerts": [],
        "chats": {
            "general": {"patient": [{"sender": "admin", "text": "hi"}, {"sender": "other", "text": "x"}]},
            "direct": {"patient": {"clin": [{"sender": "admin", "text": "y"}, {"sender": "clin", "text": "z"}]}},
        },
    }
    service.current_user = User("other", "hash", "admin", "", "", "", "", "")
    assert service.delete_user(hospital_id, "admin", "admin") is True
    general_msgs = service._data["hospitals"][hospital_id]["chats"]["general"]["patient"]
    assert all(msg["sender"] != "admin" for msg in general_msgs)
    direct_msgs = service._data["hospitals"][hospital_id]["chats"]["direct"]["patient"]["clin"]
    assert all(msg["sender"] != "admin" for msg in direct_msgs)


def test_delete_user_prevents_self_deletion(hospital_service):
    """
    Tests that a user cannot delete their own account.

    The `delete_user` method should return `False` if the user to be deleted is the same as the currently logged-in user.
    """
    service, hospital_id = hospital_service
    service._data["hospitals"][hospital_id]["users"]["self_admin"] = _make_user_record("self", "admin")
    service.current_user = User("self", "hash", "admin", "", "", "", "", "")
    assert service.delete_user(hospital_id, "self", "admin") is False


def test_delete_user_handles_missing_hospital(service):
    """
    Tests that attempting to delete a user from a non-existent hospital fails gracefully.
    """
    assert service.delete_user("missing", "user", "patient") is False


def test_get_all_clinicians_returns_only_approved(hospital_service):
    """
    Tests that `get_all_clinicians` only returns users with an 'approved' status.

    Pending clinicians should not be included in the list of active clinicians.
    """
    service, hospital_id = hospital_service
    # Set up users with different statuses
    service._data["hospitals"][hospital_id]["users"] = {
        "c1_clinician": _make_user_record("c1", "clinician", status="approved"),
        "c2_clinician": _make_user_record("c2", "clinician", status="pending"),
    }
    clinicians = service.get_all_clinicians(hospital_id)
    assert [c["username"] for c in clinicians] == ["c1"]


def test_assign_and_unassign_clinician(hospital_service):
    """
    Tests the full workflow of assigning a clinician to a patient and then unassigning them.

    Verifies that assignments are added, duplicates are prevented, and removals work as expected.
    """
    service, hospital_id = hospital_service
    patient_key = "patient_patient"
    service._data["hospitals"][hospital_id]["users"][patient_key] = _make_user_record(
        "patient", "patient", assigned_clinicians=[]
    )
    assert service.assign_clinician_to_patient(hospital_id, "patient", "clin") is True
    assert service.assign_clinician_to_patient(hospital_id, "patient", "clin") is False  # no duplicates
    assigned = service.get_assigned_clinicians_for_patient(hospital_id, "patient")
    assert assigned == ["clin"]
    assert service.unassign_clinician_from_patient(hospital_id, "patient", "clin") is True
    assert service.unassign_clinician_from_patient(hospital_id, "patient", "clin") is False


def test_search_notes_filters_by_term(hospital_service):
    """
    Tests the note search functionality.

    Verifies that providing a search term correctly filters notes based on their content (notes and diagnoses fields).
    """
    service, hospital_id = hospital_service
    service._data["hospitals"][hospital_id]["notes"] = [
        {"note_id": "n1", "patient_id": "p1", "notes": "Pain improved", "diagnoses": ""},
        {"note_id": "n2", "patient_id": "p1", "notes": "", "diagnoses": "Flu"},
    ]
    all_notes = service.search_notes(hospital_id, "p1", "")
    assert len(all_notes) == 2
    filtered = service.search_notes(hospital_id, "p1", "flu")
    assert [n["note_id"] for n in filtered] == ["n2"]


def test_alert_management(hospital_service):
    """
    Tests the alert retrieval and dismissal workflow.

    Verifies that alerts can be fetched and that `dismiss_alert` correctly removes an alert from the list.
    """
    service, hospital_id = hospital_service
    service._data["hospitals"][hospital_id]["alerts"] = [
        {"alert_id": "a1"},
        {"alert_id": "a2"},
    ]
    alerts = service.get_pain_alerts(hospital_id)
    assert len(alerts) == 2
    assert service.dismiss_alert(hospital_id, "a1") is True
    remaining_ids = [a["alert_id"] for a in service.get_pain_alerts(hospital_id)]
    assert remaining_ids == ["a2"]


def test_chat_service_general_flows(hospital_service):
    """
    Tests the core functionality of the general (care team) chat channel.

    This includes adding, retrieving, and clearing messages, and ensuring empty messages are ignored.
    """
    service, hospital_id = hospital_service
    chat = service.chat
    chats = chat._ensure_chat_store(hospital_id)
    assert set(chats) == {"general", "direct"}

    general_thread = chat._ensure_general_thread(hospital_id, "patient1")
    assert general_thread == []

    # Empty message ignored
    assert chat.add_general_message(hospital_id, "patient1", "user", "patient", "   ") is None

    message = chat.add_general_message(hospital_id, "patient1", "user", "patient", "Hello team")
    assert message["text"] == "Hello team"
    assert chat.get_general_messages(hospital_id, "patient1")[-1]["text"] == "Hello team"
    limited = chat.get_general_messages(hospital_id, "patient1", limit=1)
    assert len(limited) == 1

    assert chat.clear_general_messages(hospital_id, "patient1") is True
    assert chat.get_general_messages(hospital_id, "patient1") == []
    assert chat.clear_general_messages(hospital_id, "unknown") is False


def test_chat_service_direct_messages_require_assignment(hospital_service):
    """
    Tests that direct messages can only be sent between a patient and an assigned clinician.

    Verifies that an unassigned clinician cannot send a message and that an assigned one can.
    """
    service, hospital_id = hospital_service
    service._data["hospitals"][hospital_id]["users"]["patient_patient"] = _make_user_record(
        "patient", "patient", assigned_clinicians=["clin"]
    )
    chat = service.chat
    # attempt by unassigned
    result = chat.add_direct_message(hospital_id, "patient", "other", "other", "clinician", "Hi")
    assert result is None

    direct_thread = chat._ensure_direct_thread(hospital_id, "patient", "clin")
    assert direct_thread == []

    service._data["hospitals"][hospital_id]["users"]["patient_patient"]["assigned_clinicians"] = ["clin"]
    message = chat.add_direct_message(hospital_id, "patient", "clin", "clin", "clinician", "Hello patient")
    assert message is not None
    assert message["channel"] == "direct"

    retrieved = chat.get_direct_messages(hospital_id, "patient", "clin")
    assert retrieved[-1]["text"] == "Hello patient"
    limited = chat.get_direct_messages(hospital_id, "patient", "clin", limit=1)
    assert len(limited) == 1

    assert chat.clear_direct_messages(hospital_id, "patient", "clin") is True
    assert chat.get_direct_messages(hospital_id, "patient", "clin") == []
    assert chat.clear_direct_messages(hospital_id, "patient", "clin") is True
    assert chat.get_direct_messages(hospital_id, "patient", "clin") == []


def test_chat_service_listing_methods(hospital_service):
    """
    Tests the methods for listing active chat threads.

    Verifies that `list_general_patients` and `list_direct_threads_for_clinician` return the correct, ordered lists of participants.
    """
    service, hospital_id = hospital_service
    chat = service.chat
    service._data["hospitals"][hospital_id]["chats"]["general"] = {
        "patient1": [{"timestamp": "2024-01-01T10:00:00Z"}],
        "patient2": [{"timestamp": "2024-01-01T11:00:00Z"}],
    }
    general_patients = chat.list_general_patients(hospital_id)
    assert general_patients == ["patient2", "patient1"]

    service._data["hospitals"][hospital_id]["chats"]["direct"] = {
        "patient": {
            "clin": [
                {"timestamp": "2024-01-01T09:00:00Z"},
                {"timestamp": "2024-01-01T12:00:00Z"}
            ],
            "other": [{"timestamp": "2024-01-01T11:00:00Z"}]
        }
    }
    threads = chat.list_direct_threads_for_clinician(hospital_id, "clin")
    assert threads == ["patient"]


def test_chat_build_message_contains_metadata():
    """
    Tests that the internal `_build_message` helper correctly constructs a message dictionary.

    Verifies that all required metadata (sender, role, timestamp, ID, etc.) is included.
    """
    chat = chat_module.ChatService(
        carelog_service=types.SimpleNamespace(_data={"hospitals": {}}, _save_data=lambda: None)
    )
    message = chat._build_message("sender", "role", "text", channel="general", extra="info")
    assert message["sender"] == "sender"
    assert message["sender_role"] == "role"
    assert message["text"] == "text"
    assert message["channel"] == "general"
    assert message["extra"] == "info"
    assert message["timestamp"].endswith("Z")
    assert message["message_id"]


def test_encryption_write_and_load_key(tmp_path, monkeypatch):
    """
    Tests that an encryption key can be written to and loaded from a file.

    This verifies the basic key management functions in the encryption module.
    """
    monkeypatch.chdir(tmp_path)
    encryption_module.write_key()
    key_path = tmp_path / "secret.key"
    assert key_path.exists()
    key = encryption_module.load_key()
    assert isinstance(key, bytes)


def test_encryption_encryptor_round_trip():
    """
    Tests that data can be successfully encrypted and then decrypted back to its original form.

    This is a sanity check for the `Encryptor` class.
    """
    token = encryption_module.encryptor.encrypt(b"hello")
    assert encryption_module.encryptor.decrypt(token) == b"hello"


def test_user_model_defaults():
    """
    Tests the `User` data model.

    Verifies that the fields are correctly assigned during initialization.
    """
    user = User("user", "hash", "patient", "Full Name", "1990-01-01", "F", "she/her", "bio")
    assert user.user_id == "user"
    assert user.username == "user"
    assert user.role == "patient"


def test_patient_note_generates_ids_and_timestamps():
    """
    Tests the `PatientNote` data model.

    Verifies that a `note_id` and `timestamp` are automatically generated if not provided.
    """
    note = PatientNote(
        patient_id="p",
        author_id="a",
        mood=5,
        pain=4,
        appetite=6,
        notes="notes",
        diagnoses="diag",
        source="patient",
        hospital_id="H",
    )
    assert note.note_id
    assert note.timestamp

    custom_note = PatientNote(
        patient_id="p",
        author_id="a",
        mood=5,
        pain=4,
        appetite=6,
        notes="notes",
        diagnoses="diag",
        source="patient",
        hospital_id="H",
        note_id="custom",
        timestamp="2024-01-01T00:00:00",
    )
    assert custom_note.note_id == "custom"
    assert custom_note.timestamp == "2024-01-01T00:00:00"


def test_gemini_generate_feedback_success(monkeypatch):
    """
    Tests the successful generation of AI feedback using a mocked Gemini model.

    Verifies that the correct prompt is sent and the mocked response is returned.
    """
    prompts = []

    class DummyModel:
        def generate_content(self, prompt):
            prompts.append(prompt)

            class Response:
                text = "AI feedback"

            return Response()

    monkeypatch.setattr(gemini_module, "model", DummyModel(), raising=False)
    feedback = gemini_module.generate_feedback("Notes", 5, 4, 6)
    assert feedback == "AI feedback"
    assert "Notes" in prompts[0]


def test_gemini_generate_feedback_handles_errors(monkeypatch):
    """
    Tests that the AI feedback generation function handles runtime errors gracefully.

    If the underlying API call fails, the function should return `None` instead of crashing.
    """
    class ErrorModel:
        def generate_content(self, prompt):
            raise RuntimeError("API error")

    monkeypatch.setattr(gemini_module, "model", ErrorModel(), raising=False)
    assert gemini_module.generate_feedback("Notes", 5, 5, 5) is None


def test_format_timestamp_variations():
    """
    Tests the _format_timestamp GUI helper with various input formats.

    Verifies that it correctly handles timezone-aware inputs, naive inputs interpreted as UTC, None, and invalid strings.
    """
    now_utc = datetime.now(timezone.utc).replace(microsecond=0)
    formatted = gui_module._format_timestamp(now_utc.isoformat())
    expected_local = now_utc.astimezone().strftime("%H:%M")
    assert formatted.endswith(expected_local)

    naive_timestamp = datetime(2024, 1, 2, 12, 34, 0)
    expected_from_naive = naive_timestamp.replace(tzinfo=timezone.utc).astimezone().strftime("%H:%M")
    formatted_naive = gui_module._format_timestamp(naive_timestamp.isoformat())
    assert formatted_naive.endswith(expected_from_naive)

    iso_utc = "2024-01-02T12:34:00Z"
    expected_from_iso = datetime.fromisoformat("2024-01-02T12:34:00+00:00").astimezone().strftime("%H:%M")
    assert gui_module._format_timestamp(iso_utc).endswith(expected_from_iso)

    assert gui_module._format_timestamp(None) == "Unknown time"
    assert gui_module._format_timestamp("invalid") == "invalid"



def test_get_display_name_uses_cache(monkeypatch):
    """
    Tests that the `_get_display_name` GUI helper uses its cache to avoid redundant lookups.

    Verifies that the service method to fetch user data is only called once for the same user.
    """
    calls = []

    class StubService:
        def get_user_by_username(self, hospital_id, username, role):
            calls.append((hospital_id, username, role))
            return {"full_name": "Display"}

    cache = {}
    service = StubService()
    name1 = gui_module._get_display_name(service, "H", "user", "patient", cache)
    name2 = gui_module._get_display_name(service, "H", "user", "patient", cache)
    assert name1 == "Display"
    assert name2 == "Display"
    assert len(calls) == 1

    class EmptyService:
        def get_user_by_username(self, hospital_id, username, role):
            return {}

    cache = {}
    assert gui_module._get_display_name(EmptyService(), "H", "user", "patient", cache) == "user"
