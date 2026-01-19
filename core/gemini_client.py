import os
from dotenv import load_dotenv
from google import genai

load_dotenv()
_client = None

MODEL_FAST = os.getenv("GEMINI_MODEL_FAST", "gemini-3-flash-preview")
MODEL_DEEP = os.getenv("GEMINI_MODEL_DEEP", "gemini-3-flash-preview")  # set to pro if available

def get_client():
    global _client
    if _client is not None:
        return _client
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return None
    _client = genai.Client(api_key=api_key)
    return _client
