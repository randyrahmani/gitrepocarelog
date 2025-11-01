"""
System-level tests for the CareLog application.

These tests simulate complex, end-to-end user workflows that involve multiple
components of the system interacting. They verify the state of the system
after a series of operations to ensure data integrity and correct application flow.
"""
from modules import auth as auth_module
from modules.models import PatientNote, User


def test_end_to_end_system_state(monkeypatch, service):
    """
    Tests a full, complex workflow from hospital creation to data cleanup.

    This test covers: user registration and approval, patient-clinician assignment,
    note creation, alerting, AI feedback, chat, searching, data export, and user deletion.
    It also verifies that data remains isolated between different hospitals.
    """
    hospital_id = "SYS"
    other_hospital = "SYS2"

    assert service.register_user("primary_admin", "V4lid!Pass", "admin", hospital_id, "Admin One", "1970-01-01", "F", "she/her", "Primary admin") is True
    pending_admin = service.register_user("secondary_admin", "V4lid!Pass", "admin", hospital_id, "Admin Two", "1975-01-01", "M", "he/him", "Secondary admin")
    assert pending_admin == "pending"
    assert service.approve_user("secondary_admin", "admin", hospital_id) is True

    assert service.register_user("patient", "V4lid!Pass", "patient", hospital_id, "Patient", "1990-01-01", "F", "she/her", "Patient bio") is True
    assert service.register_user("clinician", "V4lid!Pass", "clinician", hospital_id, "Clinician", "1985-02-02", "M", "he/him", "Clin bio") == "pending"
    assert service.approve_user("clinician", "clinician", hospital_id) is True

    assert service.register_user("other_admin", "V4lid!Pass", "admin", other_hospital, "Other Admin", "1972-03-03", "F", "she/her", "Other hospital admin") is True

    service.assign_clinician_to_patient(hospital_id, "patient", "clinician")
    pain_note = PatientNote(
        patient_id="patient",
        author_id="patient",
        mood=3,
        pain=10,
        appetite=4,
        notes="Severe pain persists",
        diagnoses="",
        source="patient",
        hospital_id=hospital_id,
    )
    service.add_note(pain_note, hospital_id)
    alerts = service.get_pain_alerts(hospital_id)
    assert alerts and alerts[0]["patient_id"] == "patient"

    def fake_feedback(*args, **kwargs):
        return "Automated guidance"

    monkeypatch.setattr(auth_module, "generate_feedback", fake_feedback, raising=False)
    assert service.generate_and_store_ai_feedback(pain_note.note_id, hospital_id) is True
    assert service.approve_ai_feedback(pain_note.note_id, hospital_id, "Approved guidance") is True

    chat = service.chat
    chat.add_general_message(hospital_id, "patient", "primary_admin", "admin", "Alert received")
    chat.add_direct_message(
        hospital_id, "patient", "clinician", "clinician", "clinician", "Checking in now"
    )
    assert chat.list_general_patients(hospital_id)
    assert chat.list_direct_threads_for_clinician(hospital_id, "clinician")

    service.current_user = User("clinician", "hash", "clinician", "", "", "", "", "")
    clinician_notes = service.get_notes_for_patient(hospital_id, "patient")
    assert clinician_notes and clinician_notes[0]["ai_feedback"]["status"] == "approved"

    service.current_user = User("secondary_admin", "hash", "admin", "", "", "", "", "")
    search_hits = service.search_notes(hospital_id, "patient", "severe")
    assert search_hits and search_hits[0]["note_id"] == pain_note.note_id

    dataset = service.get_hospital_dataset(hospital_id)
    assert dataset["users"]
    assert dataset["notes"]

    service.delete_user(hospital_id, "clinician", "clinician")
    service.delete_user(hospital_id, "patient", "patient")
    assert not service.get_all_patients(hospital_id)
    assert not service.get_all_clinicians(hospital_id)

    service.dismiss_alert(hospital_id, pain_note.note_id)
    assert service.get_pain_alerts(hospital_id) == []

    # Verify other hospital data remained isolated
    other_dataset = service.get_hospital_dataset(other_hospital)
    assert other_dataset["users"]
    assert other_dataset["notes"] == []


def test_system_persistence_with_multiple_services(service):
    """
    Tests that data saved by one service instance can be correctly loaded by another.

    This verifies the data persistence layer, ensuring that the `_save_data` and
    `_load_data` cycle works as expected across different service object lifetimes.
    """
    hospital_id = "SYS_PERSIST"
    service._data["hospitals"][hospital_id] = {
        "users": {"user_patient": {"username": "user", "role": "patient"}},
        "notes": [{"note_id": "n1", "patient_id": "user"}],
        "alerts": [],
        "chats": {"general": {"user": []}, "direct": {"user": {}}},
    }
    service._save_data()

    reloaded = auth_module.CareLogService()
    assert hospital_id in reloaded.get_all_hospitals()
    assert reloaded.get_notes_for_patient(hospital_id, "user") == [{"note_id": "n1", "patient_id": "user"}]
