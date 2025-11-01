"""
This module provides the core business logic and data management for the CareLog application.

It defines the `CareLogService` class, which is responsible for:
- User authentication (registration, login, logout).
- Password hashing and verification.
- Loading and saving application data to an encrypted JSON file (`records.json`).
- Managing all data entities, including users, patient notes, and hospitals.
- Handling role-based access control for different user types (patient, clinician, admin).
- Interfacing with other services like `ChatService` and the `gemini` module for AI feedback.
"""
# carelog/modules/auth.py

import json
import hashlib
import os
from cryptography.fernet import InvalidToken
from modules.encryption import encryptor
from modules.models import User, PatientNote
from modules.gemini import generate_feedback
from modules.chat import ChatService

DATA_FILE = 'records.json'

class CareLogService:
    """Manages all business logic and data for the CareLog application."""
    def __init__(self):
        """Initializes the service, loads data, and sets up sub-services."""
        self.current_user = None
        self._data = self._load_data()
        self._ensure_hospital_defaults()
        self.chat = ChatService(self)

    def _load_data(self):
        """Loads and decrypts data from the JSON file.

        Returns:
            dict: The loaded data, or a new dictionary if the file doesn't exist or is corrupt.
        """
        try:
            with open(DATA_FILE, 'r') as f:
                encrypted_data = f.read()
                if not encrypted_data:
                    return {"hospitals": {}}
                decrypted_data = encryptor.decrypt(encrypted_data.encode()).decode()
                data = json.loads(decrypted_data)
                if 'hospitals' not in data:
                    data['hospitals'] = {}
                return data
        except (FileNotFoundError, InvalidToken, json.JSONDecodeError) as e:
            # If the file is missing, corrupt, or invalid, start with a fresh data structure.
            print(f"Warning: Could not load data file ({e}). Starting with a new dataset.")
            return {"hospitals": {}}

    def _save_data(self):
        """Encrypts and saves the current data to the JSON file."""
        with open(DATA_FILE, 'w') as f:
            data_to_encrypt = json.dumps(self._data, indent=4)
            encrypted_data = encryptor.encrypt(data_to_encrypt.encode())
            f.write(encrypted_data.decode())

    def _ensure_hospital_defaults(self):
        """Ensures that all hospital records have the default data structures."""
        hospitals = self._data.setdefault('hospitals', {})
        for hospital_id, hospital_data in hospitals.items():
            hospital_data.setdefault('users', {})
            hospital_data.setdefault('notes', [])
            hospital_data.setdefault('alerts', [])
            chats = hospital_data.setdefault('chats', {})
            chats.setdefault('general', {})
            chats.setdefault('direct', {})

    def register_user(self, username, password, role, hospital_id, full_name, dob, sex, pronouns, bio):
        """Registers a new user, handling password hashing and approval logic.

        Args:
            username (str): The user's chosen username.
            password (str): The user's plaintext password.
            role (str): The user's role (patient, clinician, or admin).
            hospital_id (str): The ID of the hospital to register under.
            full_name (str): The user's full name.
            dob (str): The user's date of birth in ISO format.
            sex (str): The user's sex.
            pronouns (str): The user's pronouns.
            bio (str): A short biography for the user.

        Returns:
            str or bool: 'weak_password', 'hospital_not_found', 'pending', True for success, or False for failure.
        """
        if not self._is_strong_password(password):
            return 'weak_password'
        is_new_hospital = hospital_id not in self._data['hospitals']

        # Only an admin can create a new hospital.
        if is_new_hospital and role != 'admin':
            return 'hospital_not_found'

        if is_new_hospital:
            self._data['hospitals'][hospital_id] = {
                "users": {},
                "notes": [],
                "alerts": [],
                "chats": {
                    "general": {},
                    "direct": {}
                }
            }
        else:
            self._ensure_hospital_defaults()
        
        hospital_users = self._data['hospitals'][hospital_id]['users']
        user_key = f"{username}_{role}"
        
        if user_key in hospital_users:
            return False

        # Hash the password with a unique salt.
        salt = os.urandom(16).hex()
        password_to_hash = salt + password
        password_hash = hashlib.sha256(password_to_hash.encode()).hexdigest()
        
        # New clinicians and admins require approval unless it's a new hospital.
        status = 'approved'
        if (role == 'admin' or role == 'clinician') and not is_new_hospital:
            status = 'pending'

        hospital_users[user_key] = {
            'username': username,
            'password_hash': password_hash,
            'role': role,
            'salt': salt,
            'status': status,
            'full_name': full_name,
            'dob': dob,
            'sex': sex,
            'pronouns': pronouns,
            'bio': bio,
            'assigned_clinicians': [] # Specific to patients
        }
        self._save_data()
        if status == 'pending':
            return 'pending'
        return True

    def _is_strong_password(self, password: str) -> bool:
        """Checks if a password meets the defined strength criteria."""
        if len(password) < 8:
            return False
        has_upper = any(c.isupper() for c in password)
        has_lower = any(c.islower() for c in password)
        has_digit = any(c.isdigit() for c in password)
        has_special = any(not c.isalnum() for c in password)
        return has_upper and has_lower and has_digit and has_special

    def login(self, username, password, role, hospital_id):
        """Authenticates a user and sets the current user session.

        Args:
            username (str): The user's username.
            password (str): The user's plaintext password.
            role (str): The user's role.
            hospital_id (str): The ID of the hospital.

        Returns:
            User or str or None: The authenticated User object, 'pending' if the account
                                is not yet approved, or None if authentication fails.
        """
        hospital_data = self._data['hospitals'].get(hospital_id)
        if not hospital_data:
            return None
        hospital_users = hospital_data.get('users', {})
        user_key = f"{username}_{role}"
        user_data = hospital_users.get(user_key)

        if user_data:
            # Check if the account is pending approval.
            if user_data.get('status') == 'pending':
                return 'pending'

            salt = user_data.get('salt')
            if not salt:
                 return 'error' # Indicates a data integrity issue.
            password_to_check = salt + password
            hash_to_check = hashlib.sha256(password_to_check.encode()).hexdigest()

            if user_data.get('password_hash') == hash_to_check:
                self.current_user = User(
                    username=user_data['username'],
                    password_hash=user_data['password_hash'],
                    role=user_data['role'],
                    full_name=user_data.get('full_name'),
                    dob=user_data.get('dob'),
                    sex=user_data.get('sex'),
                    pronouns=user_data.get('pronouns'),
                    bio=user_data.get('bio')
                )
                return self.current_user
        return None
        
    def logout(self):
        """Logs out the current user by clearing the session."""
        self.current_user = None

    def add_note(self, note: PatientNote, hospital_id: str):
        """Adds a new patient note and creates a pain alert if necessary.

        Args:
            note (PatientNote): The note object to add.
            hospital_id (str): The ID of the hospital.
        """
        if hospital_id in self._data['hospitals']:
            self._data['hospitals'][hospital_id]['notes'].append(note.__dict__)
            # Create an alert if pain is reported as 10/10.
            if note.pain == 10 and note.source == 'patient':
                alert = {"alert_id": str(note.note_id), "patient_id": note.patient_id, "timestamp": note.timestamp, "status": "new"}
                if 'alerts' not in self._data['hospitals'][hospital_id]: self._data['hospitals'][hospital_id]['alerts'] = []
                self._data['hospitals'][hospital_id]['alerts'].append(alert)
            self._save_data()

    def generate_and_store_ai_feedback(self, note_id: str, hospital_id: str) -> bool:
        """Generates AI feedback for a specific note and stores it with a 'pending' status.

        Args:
            note_id (str): The ID of the note to generate feedback for.
            hospital_id (str): The ID of the hospital.

        Returns:
            bool: True if feedback was generated and stored, False otherwise.
        """
        if hospital_id in self._data['hospitals']:
            for note in self._data['hospitals'][hospital_id]['notes']:
                if note['note_id'] == note_id:
                    notes_text = note.get('notes', '')
                    mood_val = note.get('mood', 5)
                    pain_val = note.get('pain', 5)
                    appetite_val = note.get('appetite', 5)
                    feedback = generate_feedback(notes_text, mood_val, pain_val, appetite_val)
                    if feedback:
                        note['ai_feedback'] = {
                            "text": feedback,
                            "status": "pending"
                        }
                        self._save_data()
                        return True
        return False

    def get_notes_for_patient(self, hospital_id: str, patient_id: str) -> list:
        """Retrieves all notes for a specific patient, applying access control rules.

        Args:
            hospital_id (str): The ID of the hospital.
            patient_id (str): The ID of the patient.

        Returns:
            list: A list of note dictionaries.
        """
        hospital_data = self._data['hospitals'].get(hospital_id, {})
        all_patient_notes = [n for n in hospital_data.get('notes', []) if n.get('patient_id') == patient_id]
        
        # Clinicians can only see notes for patients they are assigned to.
        if self.current_user and self.current_user.role == 'clinician':
            patient_user_key = f"{patient_id}_patient"
            patient_data = hospital_data.get('users', {}).get(patient_user_key, {})
            assigned_clinicians = patient_data.get('assigned_clinicians', [])

            if self.current_user.username in assigned_clinicians:
                # Filter out private patient notes.
                return [n for n in all_patient_notes if not (n.get('source') == 'patient' and n.get('is_private'))]
            return [] # Return no notes if not assigned.
        return all_patient_notes # Patients and admins can see all notes.

    def get_pending_feedback(self, hospital_id: str) -> list:
        """Retrieves all notes with AI feedback awaiting approval.

        Args:
            hospital_id (str): The ID of the hospital.

        Returns:
            list: A list of note dictionaries with pending feedback.
        """
        pending_feedback = []
        
        # Get a set of assigned patient IDs for efficient filtering for clinicians.
        assigned_patient_ids = None
        if self.current_user and self.current_user.role == 'clinician':
            assigned_patients_data = self.get_all_patients(hospital_id)
            assigned_patient_ids = {p['username'] for p in assigned_patients_data}

        if hospital_id in self._data['hospitals']:
            for note in self._data['hospitals'][hospital_id]['notes']:
                if note.get('ai_feedback') and note['ai_feedback']['status'] == 'pending':
                    # Clinicians only see feedback for their assigned patients.
                    if assigned_patient_ids is not None:
                        if note.get('patient_id') in assigned_patient_ids:
                            pending_feedback.append(note)
                    else: # Admins see all pending feedback.
                        pending_feedback.append(note)
        return pending_feedback

    def approve_ai_feedback(self, note_id: str, hospital_id: str, edited_feedback_text: str) -> bool:
        """Approves AI-generated feedback for a note, updating its text.

        Args:
            note_id (str): The ID of the note.
            hospital_id (str): The ID of the hospital.
            edited_feedback_text (str): The (potentially edited) feedback text to approve.

        Returns:
            bool: True if successful, False otherwise.
        """
        if hospital_id in self._data['hospitals']:
            for note in self._data['hospitals'][hospital_id]['notes']:
                if note['note_id'] == note_id:
                    if note.get('ai_feedback'):
                        note['ai_feedback']['text'] = edited_feedback_text
                        note['ai_feedback']['status'] = 'approved' 
                        self._save_data()
                        return True
        return False

    def reject_ai_feedback(self, note_id: str, hospital_id: str) -> bool:
        """Rejects and deletes AI-generated feedback for a note.

        Args:
            note_id (str): The ID of the note.
            hospital_id (str): The ID of the hospital.

        Returns:
            bool: True if successful, False otherwise.
        """
        if hospital_id in self._data['hospitals']:
            for note in self._data['hospitals'][hospital_id]['notes']:
                if note.get('note_id') == note_id:
                    if 'ai_feedback' in note:
                        del note['ai_feedback']
                        self._save_data()
                        return True
        return False

    def delete_note(self, note_id: str, hospital_id: str) -> bool:
        """Deletes a specific note.

        Args:
            note_id (str): The ID of the note to delete.
            hospital_id (str): The ID of the hospital.

        Returns:
            bool: True if successful, False otherwise.
        """
        if hospital_id in self._data['hospitals']:
            self._data['hospitals'][hospital_id]['notes'] = [n for n in self._data['hospitals'][hospital_id]['notes'] if n['note_id'] != note_id]
            self._save_data()
            return True
        return False

    def get_all_patients(self, hospital_id: str) -> list:
        """Retrieves a list of all patients in a hospital, respecting clinician assignments.

        Args:
            hospital_id (str): The ID of the hospital.

        Returns:
            list: A list of patient user data dictionaries.
        """
        hospital_users = self._data['hospitals'].get(hospital_id, {}).get('users', {})
        current_user = self.current_user
        patient_list = []
        for user_data in hospital_users.values():
            if user_data.get('role') == 'patient':
                # Clinicians only see patients they are assigned to.
                if current_user.role == 'clinician':
                    if current_user.username in user_data.get('assigned_clinicians', []):
                        patient_list.append(user_data)
                else: # Admins see all patients.
                    patient_list.append(user_data)
        return patient_list

    def get_all_users(self, hospital_id: str) -> dict:
        """Retrieves all users for a given hospital.

        Args:
            hospital_id (str): The ID of the hospital.

        Returns:
            dict: A dictionary of user data.
        """
        return self._data['hospitals'].get(hospital_id, {}).get('users', {})
        
    def get_user_by_username(self, hospital_id: str, username: str, role: str) -> dict:
        """Retrieves a single user's data by username and role.

        Args:
            hospital_id (str): The ID of the hospital.
            username (str): The user's username.
            role (str): The user's role.

        Returns:
            dict: The user's data, or an empty dictionary if not found.
        """
        user_key = f"{username}_{role}"
        return self._data['hospitals'].get(hospital_id, {}).get('users', {}).get(user_key, {})

    def get_hospital_dataset(self, hospital_id: str) -> dict:
        """Retrieves the entire dataset for a specific hospital.

        Args:
            hospital_id (str): The ID of the hospital.

        Returns:
            dict: The hospital's dataset.
        """
        return self._data['hospitals'].get(hospital_id, {"users": {}, "notes": []})

    def get_all_hospitals(self) -> list:
        """Retrieves a list of all hospital IDs.

        Returns:
            list: A list of hospital ID strings.
        """
        return list(self._data['hospitals'].keys())

    def get_pending_users(self, hospital_id: str, role: str) -> list:
        """Retrieves a list of users with a 'pending' status for a specific role.

        Args:
            hospital_id (str): The ID of the hospital.
            role (str): The role to filter by.

        Returns:
            list: A list of pending user data dictionaries.
        """
        hospital_users = self._data['hospitals'].get(hospital_id, {}).get('users', {})
        pending_users = []
        for user_key, user_data in hospital_users.items():
            if user_data.get('role') == role and user_data.get('status') == 'pending':
                pending_users.append(user_data)
        return pending_users

    def approve_user(self, username: str, role: str, hospital_id: str) -> bool:
        """Approves a pending user, changing their status to 'approved'.

        Args:
            username (str): The username of the user to approve.
            role (str): The role of the user to approve.
            hospital_id (str): The ID of the hospital.

        Returns:
            bool: True if successful, False otherwise.
        """
        hospital_users = self._data['hospitals'].get(hospital_id, {}).get('users', {})
        user_key = f"{username}_{role}"
        if user_key in hospital_users:
            hospital_users[user_key]['status'] = 'approved'
            self._save_data()
            return True
        return False

    def update_user_profile(self, hospital_id: str, username: str, role: str, details: dict) -> bool:
        """Updates a user's profile information and optionally their password.

        Args:
            hospital_id (str): The ID of the hospital.
            username (str): The username of the user to update.
            role (str): The role of the user to update.
            details (dict): A dictionary of details to update.

        Returns:
            bool: True if successful, False otherwise.
        """
        user_key = f"{username}_{role}"
        user_data = self._data['hospitals'].get(hospital_id, {}).get('users', {}).get(user_key)
        if not user_data:
            return False

        # Update profile fields.
        user_data['full_name'] = details.get('full_name', user_data.get('full_name'))
        user_data['dob'] = details.get('dob', user_data.get('dob'))
        user_data['sex'] = details.get('sex', user_data.get('sex'))
        user_data['pronouns'] = details.get('pronouns', user_data.get('pronouns'))
        user_data['bio'] = details.get('bio', user_data.get('bio'))

        # Update password if a new one is provided.
        if 'new_password' in details and details['new_password']:
            salt = os.urandom(16).hex()
            password_to_hash = salt + details['new_password']
            password_hash = hashlib.sha256(password_to_hash.encode()).hexdigest()
            user_data['salt'] = salt
            user_data['password_hash'] = password_hash

        self._save_data()
        return True

    def update_note(self, hospital_id: str, note_id: str, updated_data: dict) -> bool:
        """Updates the content of an existing note.

        Args:
            hospital_id (str): The ID of the hospital.
            note_id (str): The ID of the note to update.
            updated_data (dict): A dictionary of fields to update in the note.

        Returns:
            bool: True if successful, False otherwise.
        """
        notes = self._data['hospitals'].get(hospital_id, {}).get('notes', [])
        for note in notes:
            if note.get('note_id') == note_id:
                note.update(updated_data)
                self._save_data()
                return True
        return False

    def delete_user(self, hospital_id: str, username: str, role: str) -> bool:
        """Deletes a user and all their associated data.

        This includes their notes, chat messages, and assignments.

        Args:
            hospital_id (str): The ID of the hospital.
            username (str): The username of the user to delete.
            role (str): The role of the user to delete.

        Returns:
            bool: True if successful, False otherwise.
        """
        hospital = self._data['hospitals'].get(hospital_id)
        if not hospital:
            return False

        hospital_users = hospital.get('users', {})
        user_key = f"{username}_{role}"
        if user_key not in hospital_users:
            return False

        # Prevent an admin from deleting their own account.
        if self.current_user and self.current_user.username == username and self.current_user.role == role:
            return False

        del hospital_users[user_key]

        # Clean up all associated data for the deleted user.
        chats = hospital.setdefault('chats', {"general": {}, "direct": {}})

        if role == 'patient':
            # Remove patient's notes and chat history.
            notes = hospital.get('notes', [])
            hospital['notes'] = [n for n in notes if n.get('patient_id') != username]
            chats.get('general', {}).pop(username, None)
            chats.get('direct', {}).pop(username, None)
        elif role == 'clinician':
            # Remove clinician from patient assignments and delete their authored notes.
            for data in hospital_users.values():
                if data.get('role') == 'patient':
                    assigned = data.get('assigned_clinicians', [])
                    if assigned and username in assigned:
                        assigned.remove(username)
            notes = hospital.get('notes', [])
            hospital['notes'] = [
                n for n in notes
                if not (n.get('author_id') == username and n.get('source') == 'clinician')
            ]
            # Remove clinician from all chat threads.
            direct_threads = chats.get('direct', {})
            for patient_username, threads in direct_threads.items():
                if username in threads:
                    del threads[username]
            general_threads = chats.get('general', {})
            for patient_username, messages in general_threads.items():
                general_threads[patient_username] = [
                    msg for msg in messages if msg.get('sender') != username
                ]
        else: # Admin
            # Remove admin messages from all chat threads.
            general_threads = chats.get('general', {})
            for patient_username, messages in general_threads.items():
                general_threads[patient_username] = [
                    msg for msg in messages if msg.get('sender') != username
                ]
            direct_threads = chats.get('direct', {})
            for patient_username, threads in direct_threads.items():
                for clinician_username, messages in list(threads.items()):
                    threads[clinician_username] = [
                        msg for msg in messages if msg.get('sender') != username
                    ]

        self._save_data()
        return True

    def get_all_clinicians(self, hospital_id: str) -> list:
        """Retrieves a list of all approved clinicians in a hospital.

        Args:
            hospital_id (str): The ID of the hospital.

        Returns:
            list: A list of clinician user data dictionaries.
        """
        hospital_users = self._data['hospitals'].get(hospital_id, {}).get('users', {})
        return [data for data in hospital_users.values() if data.get('role') == 'clinician' and data.get('status') == 'approved']

    def get_assigned_clinicians_for_patient(self, hospital_id: str, patient_username: str) -> list:
        """Retrieves the list of clinicians assigned to a specific patient.

        Args:
            hospital_id (str): The ID of the hospital.
            patient_username (str): The username of the patient.

        Returns:
            list: A list of assigned clinician usernames.
        """
        patient_key = f"{patient_username}_patient"
        patient_data = self._data['hospitals'].get(hospital_id, {}).get('users', {}).get(patient_key, {})
        return patient_data.get('assigned_clinicians', []) or []

    def assign_clinician_to_patient(self, hospital_id: str, patient_username: str, clinician_username: str) -> bool:
        """Assigns a clinician to a patient.

        Args:
            hospital_id (str): The ID of the hospital.
            patient_username (str): The username of the patient.
            clinician_username (str): The username of the clinician.

        Returns:
            bool: True if successful, False otherwise.
        """
        patient_key = f"{patient_username}_patient"
        patient_data = self._data['hospitals'].get(hospital_id, {}).get('users', {}).get(patient_key)
        if patient_data:
            if 'assigned_clinicians' not in patient_data:
                patient_data['assigned_clinicians'] = []
            if clinician_username not in patient_data['assigned_clinicians']:
                patient_data['assigned_clinicians'].append(clinician_username)
                self._save_data()
                return True
        return False

    def unassign_clinician_from_patient(self, hospital_id: str, patient_username: str, clinician_username: str) -> bool:
        """Unassigns a clinician from a patient.

        Args:
            hospital_id (str): The ID of the hospital.
            patient_username (str): The username of the patient.
            clinician_username (str): The username of the clinician.

        Returns:
            bool: True if successful, False otherwise.
        """
        patient_key = f"{patient_username}_patient"
        patient_data = self._data['hospitals'].get(hospital_id, {}).get('users', {}).get(patient_key)
        if patient_data and 'assigned_clinicians' in patient_data:
            if clinician_username in patient_data['assigned_clinicians']:
                patient_data['assigned_clinicians'].remove(clinician_username)
                self._save_data()
                return True
        return False

    def search_notes(self, hospital_id: str, patient_id: str, search_term: str) -> list:
        """Searches a patient's notes for a given term.

        Args:
            hospital_id (str): The ID of the hospital.
            patient_id (str): The ID of the patient.
            search_term (str): The term to search for.

        Returns:
            list: A list of matching note dictionaries.
        """
        all_notes = self.get_notes_for_patient(hospital_id, patient_id)
        if not search_term:
            return all_notes
        
        search_term = search_term.lower()
        
        def note_matches(note):
            notes_text = note.get('notes', '').lower()
            diagnoses_text = note.get('diagnoses', '').lower()
            return search_term in notes_text or search_term in diagnoses_text

        return [note for note in all_notes if note_matches(note)]

    def get_pain_alerts(self, hospital_id: str) -> list:
        """Retrieves all active pain alerts for a hospital.

        Args:
            hospital_id (str): The ID of the hospital.

        Returns:
            list: A list of alert dictionaries.
        """
        alerts = self._data['hospitals'].get(hospital_id, {}).get('alerts', [])
        return alerts

    def dismiss_alert(self, hospital_id: str, alert_id: str) -> bool:
        """Dismisses a pain alert.

        Args:
            hospital_id (str): The ID of the hospital.
            alert_id (str): The ID of the alert to dismiss.

        Returns:
            bool: True if successful, False otherwise.
        """
        alerts = self._data['hospitals'].get(hospital_id, {}).get('alerts', [])
        self._data['hospitals'][hospital_id]['alerts'] = [a for a in alerts if a.get('alert_id') != alert_id]
        self._save_data()
        return True