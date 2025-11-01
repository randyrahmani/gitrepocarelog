"""
This module defines the `ChatService` for handling real-time messaging between patients and clinicians.

It provides functionalities for:
- Creating and managing general (care team) and direct (one-to-one) chat channels.
- Adding, retrieving, and clearing messages in these channels.
- Ensuring the underlying data structures for chat are correctly initialized within the main data store.
- Listing active chat threads for users.

The `ChatService` is tightly integrated with the main `CareLogService` to access and persist chat data.
"""
# carelog/modules/chat.py

from __future__ import annotations

from datetime import datetime
import uuid
from typing import Dict, List, Optional


class ChatService:
    """Manages patient-clinician conversations, including general and direct channels."""

    def __init__(self, carelog_service) -> None:
        """Initializes the ChatService with a reference to the main CareLogService.

        Args:
            carelog_service: An instance of the main CareLogService.
        """
        self._service = carelog_service

    def _ensure_chat_store(self, hospital_id: str) -> Dict[str, Dict]:
        """Ensures the base chat structure exists for a hospital and returns it."""
        hospitals = self._service._data.setdefault('hospitals', {})
        hospital = hospitals.setdefault(
            hospital_id,
            {
                "users": {},
                "notes": [],
                "alerts": [],
                "chats": {
                    "general": {},
                    "direct": {}
                }
            }
        )
        chats = hospital.setdefault('chats', {})
        chats.setdefault('general', {})
        chats.setdefault('direct', {})
        return chats

    def _ensure_general_thread(self, hospital_id: str, patient_username: str) -> List[Dict]:
        """Ensures a general chat thread exists for a patient and returns it."""
        chats = self._ensure_chat_store(hospital_id)
        general = chats.setdefault('general', {})
        return general.setdefault(patient_username, [])

    def _ensure_direct_thread(self, hospital_id: str, patient_username: str, clinician_username: str) -> List[Dict]:
        """Ensures a direct chat thread exists between a patient and a clinician and returns it."""
        chats = self._ensure_chat_store(hospital_id)
        direct = chats.setdefault('direct', {})
        patient_threads = direct.setdefault(patient_username, {})
        return patient_threads.setdefault(clinician_username, [])

    def add_general_message(
        self,
        hospital_id: str,
        patient_username: str,
        sender_username: str,
        sender_role: str,
        message: str
    ) -> Optional[Dict]:
        """Adds a message to the patient's general care team channel.

        Args:
            hospital_id: The ID of the hospital.
            patient_username: The username of the patient this channel belongs to.
            sender_username: The username of the message sender.
            sender_role: The role of the message sender.
            message: The text of the message.

        Returns:
            A dictionary representing the created message, or None if the message was empty.
        """
        text = (message or "").strip()
        if not text:
            return None

        thread = self._ensure_general_thread(hospital_id, patient_username)
        entry = self._build_message(
            sender_username,
            sender_role,
            text,
            channel="general",
            patient_username=patient_username
        )
        thread.append(entry)
        self._service._save_data()
        return entry

    def clear_general_messages(self, hospital_id: str, patient_username: str) -> bool:
        """Clears all messages from a patient's general care team channel.

        Args:
            hospital_id: The ID of the hospital.
            patient_username: The username of the patient.

        Returns:
            True if messages were cleared, False otherwise.
        """
        chats = self._ensure_chat_store(hospital_id)
        general = chats.setdefault('general', {})
        if patient_username in general:
            general[patient_username] = []
            self._service._save_data()
            return True
        return False

    def get_general_messages(
        self,
        hospital_id: str,
        patient_username: str,
        limit: Optional[int] = None
    ) -> List[Dict]:
        """Retrieves the ordered message history for a patient's general channel.

        Args:
            hospital_id: The ID of the hospital.
            patient_username: The username of the patient.
            limit: An optional integer to limit the number of recent messages returned.

        Returns:
            A sorted list of message dictionaries.
        """
        thread = list(self._ensure_general_thread(hospital_id, patient_username))
        thread.sort(key=lambda item: item.get("timestamp", ""))
        if limit is not None:
            return thread[-limit:]
        return thread

    def add_direct_message(
        self,
        hospital_id: str,
        patient_username: str,
        clinician_username: str,
        sender_username: str,
        sender_role: str,
        message: str
    ) -> Optional[Dict]:
        """Adds a message to the direct channel between a patient and a specific clinician.

        Args:
            hospital_id: The ID of the hospital.
            patient_username: The username of the patient.
            clinician_username: The username of the clinician.
            sender_username: The username of the message sender.
            sender_role: The role of the message sender.
            message: The text of the message.

        Returns:
            A dictionary representing the created message, or None if the message was empty
            or the sender is not authorized.
        """
        text = (message or "").strip()
        if not text:
            return None

        # Ensure the clinician is assigned to the patient before allowing a direct message.
        assigned = self._service.get_assigned_clinicians_for_patient(hospital_id, patient_username)
        if assigned and clinician_username not in assigned:
            return None

        thread = self._ensure_direct_thread(hospital_id, patient_username, clinician_username)
        entry = self._build_message(
            sender_username,
            sender_role,
            text,
            channel="direct",
            patient_username=patient_username,
            clinician_username=clinician_username
        )
        thread.append(entry)
        self._service._save_data()
        return entry

    def get_direct_messages(
        self,
        hospital_id: str,
        patient_username: str,
        clinician_username: str,
        limit: Optional[int] = None
    ) -> List[Dict]:
        """Retrieves the ordered message history between a patient and a clinician.

        Args:
            hospital_id: The ID of the hospital.
            patient_username: The username of the patient.
            clinician_username: The username of the clinician.
            limit: An optional integer to limit the number of recent messages returned.

        Returns:
            A sorted list of message dictionaries.
        """
        thread = list(self._ensure_direct_thread(hospital_id, patient_username, clinician_username))
        thread.sort(key=lambda item: item.get("timestamp", ""))
        if limit is not None:
            return thread[-limit:]
        return thread

    def clear_direct_messages(self, hospital_id: str, patient_username: str, clinician_username: str) -> bool:
        """Clears all messages from a direct message thread.

        Args:
            hospital_id: The ID of the hospital.
            patient_username: The username of the patient.
            clinician_username: The username of the clinician.

        Returns:
            True if the thread was cleared, False otherwise.
        """
        chats = self._ensure_chat_store(hospital_id)
        direct = chats.setdefault('direct', {})
        patient_threads = direct.setdefault(patient_username, {})
        if clinician_username in patient_threads:
            patient_threads[clinician_username] = []
            self._service._save_data()
            return True
        return False

    def list_general_patients(self, hospital_id: str) -> List[str]:
        """Lists patients with activity on the general channel, sorted by most recent activity.

        Args:
            hospital_id: The ID of the hospital.

        Returns:
            A list of patient usernames.
        """
        chats = self._ensure_chat_store(hospital_id)
        general = chats.get('general', {})
        patients = []
        for patient_username, messages in general.items():
            last_ts = messages[-1].get("timestamp") if messages else ""
            patients.append((patient_username, last_ts))
        patients.sort(key=lambda item: item[1] or "", reverse=True)
        return [username for username, _ in patients]

    def list_direct_threads_for_clinician(self, hospital_id: str, clinician_username: str) -> List[str]:
        """Lists patient usernames with direct chat history for a clinician, sorted by most recent activity.

        Args:
            hospital_id: The ID of the hospital.
            clinician_username: The username of the clinician.

        Returns:
            A list of patient usernames.
        """
        chats = self._ensure_chat_store(hospital_id)
        direct = chats.get('direct', {})
        patients = []
        for patient_username, clinician_threads in direct.items():
            if clinician_username in clinician_threads:
                messages = clinician_threads[clinician_username]
                last_ts = messages[-1].get("timestamp") if messages else ""
                patients.append((patient_username, last_ts))
        patients.sort(key=lambda item: item[1] or "", reverse=True)
        return [username for username, _ in patients]

    def _build_message(self, sender_username: str, sender_role: str, text: str, **extra: Dict) -> Dict:
        """Constructs a standardized chat message dictionary.

        Args:
            sender_username: The username of the sender.
            sender_role: The role of the sender.
            text: The message content.
            **extra: Additional metadata to include in the message dictionary.

        Returns:
            A dictionary representing the structured chat message.
        """
        timestamp = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        message = {
            "message_id": str(uuid.uuid4()),
            "timestamp": timestamp,
            "sender": sender_username,
            "sender_role": sender_role,
            "text": text
        }
        message.update(extra)
        return message