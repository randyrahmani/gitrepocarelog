"""
This module handles the encryption and decryption of the application's data file.

It uses the `cryptography` library (specifically Fernet symmetric encryption) to ensure that
the data at rest (`records.json`) is secure. The module is responsible for:
- Generating a secret key for encryption if one does not already exist.
- Storing and loading the secret key from a file named `secret.key`.
- Providing a global `encryptor` object that can be used throughout the application
  for consistent encryption and decryption operations.

Security Note: The `secret.key` file is critical. It must be kept secure and should not be
committed to version control. It is recommended to add `secret.key` to the `.gitignore` file.
"""
# carelog/modules/encryption.py

from cryptography.fernet import Fernet

def write_key():
    """Generates a new Fernet key and saves it to the 'secret.key' file."""
    key = Fernet.generate_key()
    with open("secret.key", "wb") as key_file:
        key_file.write(key)

def load_key() -> bytes:
    """Loads the Fernet key from the 'secret.key' file.

    Returns:
        bytes: The encryption key.
    """
    return open("secret.key", "rb").read()

# On first run, generate and save a key if it doesn't exist.
# This ensures the application is ready to use immediately after setup.
try:
    key = load_key()
except FileNotFoundError:
    print("Encryption key not found. Generating a new one...")
    write_key()
    key = load_key()
    print("New encryption key 'secret.key' has been generated.")

# Create a global Fernet instance to be used for all encryption/decryption.
encryptor = Fernet(key)

# This allows the script to be run directly to generate a key if needed.
if __name__ == '__main__':
    print("This script manages the encryption key. If 'secret.key' is not present, it will be created.")
