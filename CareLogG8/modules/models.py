"""
This module defines the primary data models for the CareLog application.

These classes are used to structure the data that is managed by the `CareLogService`
and stored in the application's database. They provide a clear and consistent
representation of the core entities within the system.
"""
# carelog/modules/models.py

from datetime import datetime
import uuid

class User:
    """Represents a user in the system, who can be a patient, clinician, or admin.

    Attributes:
        user_id (str): A unique identifier for the user (defaults to username).
        username (str): The user's login name.
        password_hash (str): The hashed version of the user's password.
        role (str): The user's role (e.g., 'patient', 'clinician', 'admin').
        full_name (str): The user's full name.
        dob (str): The user's date of birth in ISO format.
        sex (str): The user's sex.
        pronouns (str): The user's preferred pronouns.
        bio (str): A short biography for the user.
    """
    def __init__(self, username, password_hash, role, full_name, dob, sex, pronouns, bio, user_id=None):
        self.user_id = user_id or username
        self.username = username
        self.password_hash = password_hash
        self.role = role
        self.full_name = full_name
        self.dob = dob
        self.sex = sex
        self.pronouns = pronouns
        self.bio = bio

class PatientNote:
    """Represents a single clinical note or patient entry.

    Attributes:
        note_id (str): A unique identifier for the note.
        hospital_id (str): The ID of the hospital this note belongs to.
        patient_id (str): The ID of the patient this note is about.
        author_id (str): The ID of the user who created the note.
        timestamp (str): The ISO-formatted timestamp of when the note was created.
        mood (int): A self-reported mood score (0-10).
        pain (int): A self-reported pain score (0-10).
        appetite (int): A self-reported appetite score (0-10).
        notes (str): Narrative text, either from the patient or clinician.
        diagnoses (str): Formal medical diagnoses, typically entered by a clinician.
        source (str): The source of the entry ('patient' or 'clinician').
        is_private (bool): If True, the note is visible only to the patient.
        hidden_from_patient (bool): If True, the note is visible only to clinicians.
    """
    def __init__(self, patient_id, author_id, mood, pain, appetite, notes, diagnoses, source, hospital_id, is_private=False, hidden_from_patient=False, note_id=None, timestamp=None):
        # A unique ID is generated if one is not provided.
        self.note_id = note_id or str(uuid.uuid4())
        self.hospital_id = hospital_id
        self.patient_id = patient_id
        self.author_id = author_id
        # A timestamp is generated if one is not provided.
        self.timestamp = timestamp or datetime.now().isoformat()
        self.mood = mood
        self.pain = pain
        self.appetite = appetite
        self.notes = notes
        self.diagnoses = diagnoses
        self.source = source
        self.is_private = is_private
        self.hidden_from_patient = hidden_from_patient