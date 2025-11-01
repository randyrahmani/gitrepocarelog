"""
Pytest configuration file for the CareLog test suite.

This file defines shared fixtures and setup functions used across different test files.
It includes logic to:
- Create "dummy" or "mock" versions of heavy external dependencies like `cryptography`
  and `google.generativeai`. This allows tests to run quickly and without requiring
  the actual packages to be installed or API keys to be configured.
- Define fixtures for creating isolated instances of the `CareLogService` for testing.
- Set up a temporary file system for storing test data, ensuring that tests do not
  interfere with each other or with production data.
"""
import base64
import os
import sys
import types
from pathlib import Path
import pytest


def _ensure_dummy_fernet():
    """Provide a lightweight Fernet substitute when cryptography is unavailable."""
    if "cryptography.fernet" in sys.modules:
        return

    # Dynamically create stub modules to avoid ImportError if cryptography is not installed.
    cryptography_module = types.ModuleType("cryptography")
    fernet_module = types.ModuleType("cryptography.fernet")

    class InvalidToken(Exception):
        """Raised when decryption fails."""

    class DummyFernet:
        """A simple, reversible substitute for Fernet for testing purposes."""
        def __init__(self, key):
            self.key = key

        @staticmethod
        def generate_key():
            return base64.urlsafe_b64encode(os.urandom(32))

        def encrypt(self, data: bytes) -> bytes:
            # A simple, non-secure, but reversible operation.
            return base64.urlsafe_b64encode(data[::-1])

        def decrypt(self, token: bytes) -> bytes:
            try:
                decoded = base64.urlsafe_b64decode(token)
            except Exception as exc:
                raise InvalidToken from exc
            plain = decoded[::-1]
            try:
                plain.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise InvalidToken from exc
            return plain

    fernet_module.Fernet = DummyFernet
    fernet_module.InvalidToken = InvalidToken
    cryptography_module.fernet = fernet_module
    sys.modules["cryptography"] = cryptography_module
    sys.modules["cryptography.fernet"] = fernet_module


_ensure_dummy_fernet()

from cryptography.fernet import Fernet  # noqa: E402


def _ensure_dummy_generative_ai():
    """Provide a minimal stub for google.generativeai if the package is absent."""
    if "google.generativeai" in sys.modules:
        return

    # Dynamically create stub modules to avoid ImportError if google.generativeai is not installed.
    generativeai_module = types.ModuleType("google.generativeai")

    def configure(api_key=None):
        """Dummy configure function to track the API key."""
        generativeai_module.last_configured_key = api_key

    class DummyGenerativeModel:
        """A dummy model that records prompts and returns a fixed response."""
        def __init__(self, model_name):
            self.model_name = model_name
            self.prompts = []

        def generate_content(self, prompt):
            self.prompts.append(prompt)

            class _Response:
                def __init__(self, text):
                    self.text = text

            return _Response("stubbed response")

    generativeai_module.configure = configure
    generativeai_module.GenerativeModel = DummyGenerativeModel
    try:
        import google as google_module  # type: ignore
    except ModuleNotFoundError:
        # If the 'google' package doesn't exist at all, create a dummy package.
        google_module = types.ModuleType("google")
        google_module.__path__ = []  # Mark as a package to allow nested modules.
        sys.modules["google"] = google_module
    setattr(google_module, "generativeai", generativeai_module)
    sys.modules["google.generativeai"] = generativeai_module


def _ensure_streamlit_secret():
    """Guarantee that the GEMINI secret exists so module imports succeed."""
    project_root = Path(__file__).resolve().parents[1]
    secrets_dir = project_root / ".streamlit"
    secrets_dir.mkdir(exist_ok=True)
    secrets_file = secrets_dir / "secrets.toml"
    if not secrets_file.exists():
        secrets_file.write_text('GEMINI_API_KEY = "dummy"\n', encoding="utf-8")


_ensure_dummy_generative_ai()
_ensure_streamlit_secret()

from modules import auth as auth_module  # noqa: E402


class DummyEncryptor:
    """Simple symmetric encryptor for isolating tests from the production key."""

    def __init__(self):
        self._fernet = Fernet(Fernet.generate_key())

    def encrypt(self, data: bytes) -> bytes:
        return self._fernet.encrypt(data)

    def decrypt(self, token: bytes) -> bytes:
        return self._fernet.decrypt(token)


@pytest.fixture
def dummy_encryptor():
    """Provides a `DummyEncryptor` instance for test isolation."""
    return DummyEncryptor()


@pytest.fixture
def service(tmp_path, monkeypatch, dummy_encryptor):
    data_file = tmp_path / "records.json"
    monkeypatch.setattr(auth_module, "DATA_FILE", str(data_file), raising=False)
    monkeypatch.setattr(auth_module, "encryptor", dummy_encryptor, raising=False)

    # Create a new service instance for each test.
    svc = auth_module.CareLogService()
    # Start with a clean data dictionary to ensure test isolation.
    svc._data = {"hospitals": {}}
    return svc


@pytest.fixture
def hospital_service(service):
    """
    Provides a service instance that is pre-populated with a test hospital.

    This fixture builds on the `service` fixture, adding a default hospital
    with an empty data structure. This simplifies tests that need to operate
    within the context of an existing hospital.

    Yields:
        tuple: A tuple containing the `CareLogService` instance and the `hospital_id`
               of the created test hospital.
    """
    hospital_id = "H1"
    service._data["hospitals"][hospital_id] = {
        "users": {},
        "notes": [],
        "alerts": [],
        "chats": {"general": {}, "direct": {}},
    }
    return service, hospital_id
