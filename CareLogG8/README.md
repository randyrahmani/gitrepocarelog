# CareLog: A Secure, Multi-Hospital Patient Care Platform

CareLog is a comprehensive, multi-hospital web application designed to facilitate seamless communication and data management between patients, clinicians, and administrators. Built with Python and Streamlit, it provides a secure, role-based environment for logging patient notes, managing care, and leveraging AI for supportive feedback.

---

## Key Features

CareLog offers a distinct set of features tailored to each user role, ensuring a focused and efficient user experience.

### For Patients
*   **Daily Health Journaling**: Log daily entries for mood, pain, appetite, and narrative notes.
*   **Private Entries**: Option to mark entries as private, visible only to the patient.
*   **View Care History**: Access a complete history of personal entries and clinician notes.
*   **Secure Messaging**: Communicate directly with assigned clinicians or post in a general "Care Team" channel.
*   **AI-Powered Feedback**: Request AI-generated feedback on journal entries, which is reviewed by a clinician before being shared.
*   **Profile Management**: Update personal information, bio, and password.

### For Clinicians
*   **Patient Dashboard**: View and manage a list of assigned patients.
*   **Comprehensive Note Viewing**: Browse patient histories, with full-text search capabilities.
*   **Add Clinical Notes**: Create detailed clinical notes, including diagnoses and narrative observations.
*   **Note Privacy Control**: Choose whether a clinical note is visible to the patient.
*   **Pain Alerts**: Receive and acknowledge high-priority alerts for patients reporting extreme pain (10/10).
*   **AI Feedback Review**: Review, edit, and approve or reject AI-generated feedback before it's sent to the patient.
*   **Secure Messaging**: Engage in direct, one-on-one chats with patients or participate in the care team channel.

### For Administrators
*   **User Management**: Approve pending user registrations (clinicians, admins), edit user profiles, and delete accounts.
*   **Direct User Creation**: Create new user accounts for any role directly from the admin panel.
*   **Clinician-Patient Assignment**: Easily assign and unassign clinicians to patients to manage care teams and communication channels.
*   **Data Export**: Export all hospital-specific data in multiple formats:
    *   Raw `JSON` backup.
    *   `CSV` files for users and notes.
    *   Human-readable `.txt` report of all notes.

### Core Platform Features
*   **Multi-Hospital Architecture**: Data is strictly segregated by a unique `hospital_id`, ensuring privacy between institutions.
*   **Role-Based Access Control (RBAC)**: Granular permissions ensure users only see the data and features relevant to their role.
*   **Encryption at Rest**: All application data is stored in an encrypted `records.json` file using Fernet symmetric encryption.
*   **Secure Authentication**: User passwords are not stored directly; they are hashed with a unique salt per user.

---

## Tech Stack

*   **Backend & Frontend**: Python, Streamlit
*   **AI & Generative Language**: Google Gemini API (`gemma-3-27b-it`)
*   **Data Storage**: Encrypted JSON file
*   **Data Handling**: Pandas (for CSV exports)
*   **Encryption**: Cryptography (Fernet)
*   **UI Components**: streamlit-autorefresh (for real-time chat updates)

---

## Getting Started

Follow these steps to set up and run the CareLog application on your local machine.

### Prerequisites

*   Python 3.9 or higher
*   `pip` (Python package installer)

### 1. Clone the Repository

```bash
git clone https://github.com/your-username/CareLogG8.git
cd CareLogG8
```

### 2. Install Dependencies

Create a `requirements.txt` file with the following content:

```txt
streamlit
google-generativeai
cryptography
pandas
streamlit-autorefresh
```

Then, install the required packages:

```bash
pip install -r requirements.txt
```

### 3. Configure API Key

CareLog uses Streamlit's secrets management for the Gemini API key.

1.  Create a directory `.streamlit` in the root of the project folder.
2.  Inside `.streamlit`, create a file named `secrets.toml`.
3.  Add your Gemini API key to this file:

    ```toml
    # .streamlit/secrets.toml
    GEMINI_API_KEY = "YOUR_API_KEY_HERE"
    ```

### 4. Run the Application

Execute the following command from the root directory of the project:

```bash
streamlit run main.py
```

The application will open in your default web browser.

---

## Application Flow and Usage

### First Run

On the very first run, the application will automatically:
1.  Generate a `secret.key` file. This file is crucial for encrypting and decrypting your data. **Do not delete or share it.**
2.  Create an empty, encrypted `records.json` file to store all application data.

### Creating the First Hospital and Admin

The system is designed to be self-starting.

1.  Navigate to the application in your browser.
2.  Click "Create a New Account".
3.  Select the role **"admin"**.
4.  Enter a **new, unique Hospital ID**. This action will create the hospital.
5.  Fill in the remaining details and register.

This first admin account is automatically approved and can now manage the newly created hospital, including approving other users.

### User Approval Workflow

*   **Patients**: Patient accounts are automatically approved upon registration for an existing hospital.
*   **Clinicians & Admins**: When a clinician or a new admin registers for an *existing* hospital, their account is set to "pending" and must be approved by a current administrator of that hospital.

---

## Security

Security is a core design principle of CareLog.

*   **Data Encryption**: The `records.json` data file is fully encrypted using the `cryptography` library. The application cannot read the data without the corresponding `secret.key`.
*   **Secret Key Management**: The `secret.key` file is generated locally and is not tracked by Git (it should be added to your `.gitignore` file). Losing this key will result in irreversible loss of access to all data.
*   **Password Hashing**: Passwords are never stored in plaintext. They are hashed using SHA-256 with a unique, randomly generated salt for each user, making them resilient to rainbow table attacks.
*   **API Key Security**: The Google Gemini API key is securely managed through Streamlit's built-in secrets handling and is not hardcoded in the source.

---

## Project Structure

```
CareLogG8/
├── .streamlit/
│   └── secrets.toml        # Stores API keys and other secrets
├── modules/
│   ├── auth.py             # Core business logic, data management (CareLogService)
│   ├── chat.py             # Manages real-time messaging (ChatService)
│   ├── encryption.py       # Handles data file encryption and key management
│   ├── gemini.py           # Interface for the Google Gemini API
│   └── models.py           # Defines data models (User, PatientNote)
├── gui.py                  # Contains all Streamlit UI rendering functions
├── main.py                 # Main entry point for the Streamlit application
├── records.json            # Encrypted application data store
├── secret.key              # Encryption key (auto-generated, DO NOT COMMIT)
├── requirements.txt        # Python dependencies
└── README.md               # This file
```
