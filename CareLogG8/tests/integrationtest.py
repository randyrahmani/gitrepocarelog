"""
Integration tests for the CareLog application.

These tests verify the interactions between different modules of the application,
such as the `CareLogService` and the `ChatService`, to ensure they work together
correctly to fulfill a user workflow. They are more focused than system tests
but broader than unit tests.
"""
from modules import auth as auth_module
from modules.models import PatientNote, User


def test_patient_clinician_workflow(monkeypatch, service):
    """
    Tests the integrated workflow of registering, assigning, and interacting
    between a patient and a clinician.

    This test covers registration, approval, assignment, note creation, AI feedback,
    and chat functionalities, ensuring the components integrate correctly.
    """
    hospital_id = "HOSPITAL"
    admin_info = dict(
        full_name="Admin",
        dob="1970-01-01",
        sex="F",
        pronouns="she/her",
        bio="Administrator",
    )
    assert service.register_user("admin", "V4lid!Pass", "admin", hospital_id, **admin_info) is True
    assert service.login("admin", "V4lid!Pass", "admin", hospital_id)

    patient_info = dict(
        full_name="Patient One",
        dob="1990-02-02",
        sex="M",
        pronouns="he/him",
        bio="Patient bio",
    )
    assert service.register_user("patient", "V4lid!Pass", "patient", hospital_id, **patient_info) is True

    clinician_info = dict(
        full_name="Clin One",
        dob="1985-03-03",
        sex="F",
        pronouns="she/her",
        bio="Clin bio",
    )
    pending = service.register_user("clin", "V4lid!Pass", "clinician", hospital_id, **clinician_info)
    assert pending == "pending"
    assert service.approve_user("clin", "clinician", hospital_id) is True

    service.logout()
    assert isinstance(service.login("clin", "V4lid!Pass", "clinician", hospital_id), User)

    assert service.assign_clinician_to_patient(hospital_id, "patient", "clin") is True
    note = PatientNote(
        patient_id="patient",
        author_id="patient",
        mood=7,
        pain=8,
        appetite=6,
        notes="Feeling better today",
        diagnoses="",
        source="patient",
        hospital_id=hospital_id,
    )
    service.add_note(note, hospital_id)

    def fake_feedback(*args, **kwargs):
        return "AI insight"

    monkeypatch.setattr(auth_module, "generate_feedback", fake_feedback, raising=False)
    assert service.generate_and_store_ai_feedback(note.note_id, hospital_id) is True
    pending_feedback = service.get_pending_feedback(hospital_id)
    assert len(pending_feedback) == 1
    assert service.approve_ai_feedback(note.note_id, hospital_id, "Reviewed feedback") is True

    service.current_user = User("clin", "hash", "clinician", "", "", "", "", "")
    clinician_notes = service.get_notes_for_patient(hospital_id, "patient")
    assert clinician_notes and clinician_notes[0]["note_id"] == note.note_id
    assert service.get_pending_feedback(hospital_id) == []

    chat = service.chat
    general_entry = chat.add_general_message(hospital_id, "patient", "clin", "clinician", "Check-in complete")
    assert general_entry["channel"] == "general"
    direct_entry = chat.add_direct_message(
        hospital_id, "patient", "clin", "clin", "clinician", "Private message"
    )
    assert direct_entry["channel"] == "direct"
    assert chat.get_general_messages(hospital_id, "patient")
    assert chat.get_direct_messages(hospital_id, "patient", "clin")

    service.current_user = User("admin", "hash", "admin", "", "", "", "", "")
    search_results = service.search_notes(hospital_id, "patient", "better")
    assert search_results and search_results[0]["note_id"] == note.note_id
    assert service.get_all_patients(hospital_id)
    assert service.get_all_clinicians(hospital_id)


def test_data_persistence_across_service_instances(service):
    """
    Tests that data persists correctly between different instances of the service.

    This integration test ensures that when one service instance saves data, a new
    instance can load and access that same data, verifying the file-based persistence.
    """
    hospital_id = "PERSIST"
    service._data["hospitals"][hospital_id] = {
        "users": {},
        "notes": [{"note_id": "n1"}],
        "alerts": [],
        "chats": {"general": {}, "direct": {}},
    }
    service._save_data()

    new_service = auth_module.CareLogService()
    assert hospital_id in new_service.get_all_hospitals()
    dataset = new_service.get_hospital_dataset(hospital_id)
    assert dataset["notes"] == [{"note_id": "n1"}]
