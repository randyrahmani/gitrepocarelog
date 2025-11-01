"""
This module provides an interface to the Google Gemini large language model.

It is responsible for:
- Configuring the Gemini API with the necessary credentials from Streamlit secrets.
- Initializing the generative model.
- Providing a function `generate_feedback` that constructs a prompt from patient data
  and calls the Gemini API to generate empathetic and useful feedback.

This abstracts the AI integration, making it easy to call from other parts of the application.
"""

import streamlit as st
import google.generativeai as genai

# Configure the Gemini API using the key stored in Streamlit secrets.
# This is the recommended way to handle sensitive keys in a Streamlit app.
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])

# Initialize the generative model. 'gemma-3-27b-it' is specified as the model to use.
model = genai.GenerativeModel('gemma-3-27b-it')

def generate_feedback(patient_notes: str, mood: int, pain: int, appetite: int) -> str | None:
    """Generates AI-powered feedback for a patient based on their daily entry.

    This function constructs a detailed prompt that includes the patient's self-reported
    metrics and narrative notes. It then sends this prompt to the Gemini model and
    returns the generated text.

    Args:
        patient_notes: The narrative notes provided by the patient.
        mood: The patient's self-reported mood score (0-10).
        pain: The patient's self-reported pain score (0-10).
        appetite: The patient's self-reported appetite score (0-10).

    Returns:
        The generated feedback as a string, or None if an error occurs.
    """

    # The prompt is carefully engineered to guide the AI to provide empathetic,
    # encouraging, and safe feedback suitable for a healthcare context.
    prompt = f"""
    You are an AI in a hospital that gives feedback to patients based on their notes. 
    The patient reported the following:
    - Mood: {mood}/10
    - Pain: {pain}/10
    - Appetite: {appetite}/10

    Patient Notes:
    {patient_notes}

    Provide useful feedbacks and things that the patients can do to make themselves feel better. Be kind and encouraging. 
    Do not assume things. Provide one paragraph of around 200 words. Only print the paragraph and nothing else. 


    Feedback:
    """

    try:
        # Call the Gemini API to generate content based on the prompt.
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        # In a production environment, this error should be logged more robustly.
        print(f"Error generating feedback from Gemini API: {e}")
        return None