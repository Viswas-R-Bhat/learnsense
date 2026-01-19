from typing import Optional, List, Union
from google.genai import types
from google.genai.errors import ClientError

from .gemini_client import get_client, MODEL_DEEP
from .utils import safe_json_load, clamp
from .prompts import prompt_diagnose

def diagnose(
    question: str,
    student_text: str,
    memory_block: str,
    mode: str,
    topic: str,
    image_bytes: Optional[bytes] = None,
    image_mime: Optional[str] = None,
) -> dict:
    client = get_client()
    if client is None:
        return {"error": True, "error_message": "Model unavailable."}

    prompt = prompt_diagnose(question, student_text, memory_block, mode, topic)

    contents: List[Union[str, types.Part]] = [prompt]
    if image_bytes:
        mime = image_mime or "image/jpeg"
        try:
            contents.append(types.Part.from_bytes(data=image_bytes, mime_type=mime))
        except Exception:
            pass

    try:
        resp = client.models.generate_content(model=MODEL_DEEP, contents=contents)
        parsed = safe_json_load(getattr(resp, "text", "") or "")
        if not parsed:
            return {"error": True, "error_message": "Invalid model JSON."}

        parsed["confidence"] = clamp(parsed.get("confidence", 0.5), 0.0, 1.0)
        parsed.setdefault("steps", [])
        parsed.setdefault("wrong_step_index", -1)
        parsed.setdefault("fix", "")
        parsed.setdefault("misconceptions", [])
        return parsed

    except ClientError:
        return {"error": True, "error_message": "Model busy, try again."}
    except Exception:
        return {"error": True, "error_message": "Diagnosis failed."}
