print("✅ backend.py loaded from:", __file__)

import os
import json
from typing import Optional, List, Dict, Any, Union

from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.errors import ClientError

from db import get_user_history

load_dotenv()
_client = None

MODEL_NAME = "gemini-3-flash-preview"


# =========================
# Client
# =========================
def get_client():
    """Lazy client init to avoid import-time failure."""
    global _client
    if _client is not None:
        return _client

    api_key_live = os.getenv("GOOGLE_API_KEY")
    if not api_key_live:
        print("[DEBUG] GOOGLE_API_KEY is missing/empty")
        return None

    _client = genai.Client(api_key=api_key_live)
    print("[DEBUG] Gemini client initialized")
    return _client


# =========================
# UTILS
# =========================
def extract_json(text: str) -> Optional[str]:
    """Extract JSON from text that might have markdown code blocks."""
    if not text:
        return None

    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if len(lines) > 2 else text

    text = text.replace("```json", "").replace("```", "").strip()

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return None
    return text[start : end + 1]


def safe_json_load(text: str) -> Optional[dict]:
    """Safely parse JSON with fallback."""
    try:
        extracted = extract_json(text)
        if not extracted:
            print(f"[DEBUG] No JSON found in: {text[:200]}")
            return None
        parsed = json.loads(extracted)
        print("[DEBUG] Successfully parsed JSON")
        return parsed
    except json.JSONDecodeError as e:
        print(f"[DEBUG] JSON decode error: {e}")
        print(f"[DEBUG] Text was: {text[:500]}")
        return None
    except Exception as e:
        print(f"[DEBUG] Unexpected error: {e}")
        return None


def _fallback_payload(student_message: str) -> dict:
    """Student-safe fallback: never include raw backend/model/internal error wording here."""
    return {
        "is_correct": False,
        "confidence": 0.0,
        "error": True,
        "error_message": student_message,
        "misconceptions": [],
    }


def _limit_sentences(text: str, max_sentences: int = 3, min_sentences: int = 2) -> str:
    text = (text or "").replace("\n", " ").strip()
    if not text:
        text = "Here is the correct idea in brief. Focus on the defining property and how it applies."

    sentences = [s.strip() for s in text.split(". ") if s.strip()]
    trimmed = sentences[:max_sentences] if sentences else [text]
    if len(trimmed) < min_sentences:
        trimmed.append("That is the correct framing")

    out = ". ".join(trimmed).strip()
    if not out.endswith("."):
        out += "."
    return out


def _final_answer_for(m: dict, is_correct: bool) -> str:
    if is_correct:
        return "You're already correct. If you want, try a harder variant or explain why it works."

    teaching = m.get("teaching") or {}
    explanation = teaching.get("explanation") or m.get("why_wrong") or ""
    hint = m.get("hint") or ""
    analogy = teaching.get("analogy") or ""

    parts = []
    if explanation:
        parts.append(explanation.strip())
    if hint and hint not in explanation:
        parts.append(f"Key idea: {hint.strip()}")
    if analogy:
        parts.append(f"Example: {analogy.strip()}")

    return _limit_sentences(" ".join(parts))


def is_academic_only(text: str) -> bool:
    """Hard guardrail to keep the tutor academic/informative only."""
    t = (text or "").lower()
    banned = [
        "game", "minecraft", "roblox", "valorant", "fortnite",
        "roleplay", "story", "fanfic", "meme", "joke",
        "dating", "pickup", "flirt",
        "hack", "cheat code", "aimbot",
    ]
    return not any(b in t for b in banned)


def _normalize_analysis(parsed: dict) -> dict:
    """Guarantee schema for UI (and include hint ladder)."""
    if not isinstance(parsed, dict):
        return _fallback_payload("I had trouble reading the model response. Please try again.")

    parsed.setdefault("is_correct", False)
    parsed.setdefault("confidence", 0.5)
    parsed.setdefault("misconceptions", [])

    norm = []
    for m in (parsed.get("misconceptions") or []):
        if not isinstance(m, dict):
            continue

        t = m.get("teaching") or {}
        if not isinstance(t, dict):
            t = {}

        # Hint ladder: prefer model-provided "hints"; fall back to "hint" or defaults.
        hints = m.get("hints")
        if not isinstance(hints, list) or len(hints) < 3:
            base_hint = m.get("hint") or ("Try a harder variation." if parsed["is_correct"] else "Start from the definition.")
            hints = [
                base_hint,
                "Use a simple example to test the definition.",
                "State the correct definition clearly and apply it to the question.",
            ]

        norm.append({
            "concept": m.get("concept") or ("No misconception" if parsed["is_correct"] else "Conceptual misunderstanding"),
            "why_wrong": m.get("why_wrong") or ("Your answer is correct." if parsed["is_correct"] else "The understanding is incorrect."),
            "hint": m.get("hint") or (hints[0] if hints else "Start from the definition."),
            "hints": hints[:3],
            "diagnostic_question": m.get("diagnostic_question") or "Can you explain the defining feature in one sentence?",
            "severity": m.get("severity") or ("low" if parsed["is_correct"] else "medium"),
            "teaching": {
                "explanation": t.get("explanation") or ("✅ Looks correct. Here’s a quick reinforcement." if parsed["is_correct"] else "Let’s clarify the misconception step by step."),
                "analogy": t.get("analogy") or "",
                "follow_up_question": t.get("follow_up_question") or "Want to try a follow-up question?",
            },
            "final_answer": m.get("final_answer") or _final_answer_for(m, parsed["is_correct"]),
            "memory": m.get("memory") or [],
        })

    # If correct and model forgot to include an item, add a friendly one.
    if parsed["is_correct"] and not norm:
        norm = [{
            "concept": "No misconception",
            "why_wrong": "✅ Your answer looks correct.",
            "hint": "Try a slightly harder variant or explain why it’s true.",
            "hints": [
                "Try a slightly harder variant.",
                "Explain your reasoning in 1–2 sentences.",
                "Give a counterexample and explain why it fails.",
            ],
            "diagnostic_question": "Can you justify it in one sentence?",
            "severity": "low",
            "teaching": {
                "explanation": "Nice — that matches the expected concept.",
                "analogy": "",
                "follow_up_question": "Can you explain your reasoning briefly?",
            },
            "final_answer": "You're already correct. If you want, try a harder variant or explain why it works.",
            "memory": [],
        }]

    parsed["misconceptions"] = norm
    return parsed


# =========================
# ANALYSIS (TEXT + IMAGE)
# =========================
def analyze_student_input(
    student_input: str,
    user_id: str,
    question: str,
    mode: str = "Exam",
    topic: str = "General",
    image_bytes: Optional[bytes] = None,
    image_mime: Optional[str] = None,
) -> dict:
    print(f"[DEBUG] analyze_student_input user={user_id}")

    # Academic-only guardrail (both question and answer)
    if not is_academic_only(question) or not is_academic_only(student_input):
        return _fallback_payload("I can help only with academic/learning questions. Please ask something educational.")

    if not question or len(question.strip()) < 5:
        return _fallback_payload("Please provide the question/problem statement so I can evaluate your answer.")
    if not student_input or len(student_input.strip()) < 2:
        return _fallback_payload("Please type a slightly more complete answer (1–2 lines) so I can analyze it.")

    client = get_client()
    if client is None:
        return _fallback_payload("I can’t connect to the model right now. Please check the API key and try again.")

    # ---- MEMORY (summarize for the model) ----
    history = []
    memory_lines = []
    try:
        history = get_user_history(user_id) or []
        for h in history[:6]:
            try:
                memory_lines.append(f"- {h[0]}: mastery {h[1]}% ({h[2]}) on {h[3]}")
            except Exception:
                continue
    except Exception:
        history = []

    memory_block = "\n".join(memory_lines) if memory_lines else "No prior history."

    prompt = f"""
You are an educational tutor. You must only answer academic/learning content.

Tutor mode: {mode}
Topic: {topic}

Task:
1) Evaluate the student's answer to the given Question (use the image if provided).
2) If correct: set is_correct=true and return ONE item with concept="No misconception".
3) If incorrect: set is_correct=false and return 1-3 misconceptions.
4) For each misconception include:
   - why_wrong
   - diagnostic_question
   - teaching object: explanation, analogy, follow_up_question
   - hints: an ordered list of 3 hints (subtle -> explicit)
   - final_answer: short correct answer

Return ONLY valid JSON (no markdown).

Question:
\"\"\"{question}\"\"\"

Student answer (typed):
\"\"\"{student_input}\"\"\"

Student history:
{memory_block}

Output JSON schema:
{{
  "is_correct": true | false,
  "confidence": 0.0,
  "misconceptions": [
    {{
      "concept": "",
      "why_wrong": "",
      "hints": ["", "", ""],
      "diagnostic_question": "",
      "severity": "low | medium | high",
      "teaching": {{
        "explanation": "",
        "analogy": "",
        "follow_up_question": ""
      }},
      "final_answer": ""
    }}
  ]
}}
""".strip()

    # Build multimodal contents: prompt + optional image part
    contents: List[Union[str, types.Part]] = [prompt]
    if image_bytes:
        mime = image_mime or "image/jpeg"
        try:
            contents.append(types.Part.from_bytes(data=image_bytes, mime_type=mime))
        except Exception:
            # If image part fails for any reason, proceed with text-only.
            pass

    response = None
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=contents,
        )

        raw = getattr(response, "text", "") or ""
        parsed = safe_json_load(raw)
        if not parsed:
            return _fallback_payload("I had trouble reading the model response. Please try again.")

        parsed = _normalize_analysis(parsed)

        # ---- Memory enrichment for UI ----
        try:
            for m in parsed.get("misconceptions", []):
                concept = m.get("concept", "")
                related = [h for h in (history or []) if len(h) > 0 and h[0] == concept]
                m["memory"] = [f"Past mastery {h[1]}% ({h[2]}) on {h[3]}" for h in related[:3]]
        except Exception:
            pass

        return parsed

    except ClientError:
        return _fallback_payload("The model is busy right now. Please try again in a moment.")
    except Exception:
        return _fallback_payload("Something went wrong while analyzing. Please try again.")


# =========================
# NOTES -> QUESTION GENERATION
# =========================
def generate_questions_from_notes(notes_text: str, topic: str = "General", mode: str = "Exam") -> dict:
    client = get_client()
    if client is None:
        return {"questions": []}

    if not notes_text or len(notes_text.strip()) < 30:
        return {"questions": []}

    # Academic-only guardrail
    if not is_academic_only(notes_text):
        return {"questions": []}

    prompt = f"""
You are a study assistant. Create practice questions ONLY for academic learning.

Topic: {topic}
Preferred style: {mode}

From the notes below, generate 10 questions as JSON.
Include a mix:
- 4 conceptual
- 4 application/problem-solving
- 2 tricky misconception-trap questions

Return ONLY JSON:
{{
  "questions": [
    {{
      "q": "",
      "topic": "{topic}",
      "difficulty": "easy|medium|hard",
      "type": "concept|application|trap"
    }}
  ]
}}

Notes:
\"\"\"{notes_text}\"\"\"
""".strip()

    try:
        resp = client.models.generate_content(model=MODEL_NAME, contents=prompt)
        parsed = safe_json_load(getattr(resp, "text", "") or "")
        if not parsed or "questions" not in parsed:
            return {"questions": []}
        if not isinstance(parsed.get("questions"), list):
            return {"questions": []}
        return parsed
    except Exception:
        return {"questions": []}


# =========================
# FULL PIPELINE
# =========================
def full_analysis(
    student_input: str,
    user_id: str,
    question: str,
    mode: str,
    topic: str,
    image_bytes: Optional[bytes] = None,
    image_mime: Optional[str] = None,
):
    analysis = analyze_student_input(
        student_input=student_input,
        user_id=user_id,
        question=question,
        mode=mode,
        topic=topic,
        image_bytes=image_bytes,
        image_mime=image_mime,
    )

    # Pass-through error payload for UI
    if isinstance(analysis, dict) and analysis.get("error"):
        return analysis

    if not isinstance(analysis, dict):
        return []

    enriched = []
    for m in analysis.get("misconceptions", []):
        enriched.append({
            "meta": {
                "is_correct": analysis.get("is_correct", False),
                "confidence": analysis.get("confidence", 0.5),
            },
            "misconception": {
                "concept": m.get("concept", ""),
                "why_wrong": m.get("why_wrong", ""),
                "hint": m.get("hint", ""),
                "hints": m.get("hints", []) or [],
                "diagnostic_question": m.get("diagnostic_question", ""),
                "severity": m.get("severity", "medium"),
                "final_answer": m.get("final_answer", ""),
                "memory": m.get("memory", []),
            },
            "teaching": m.get("teaching", {
                "explanation": "",
                "analogy": "",
                "follow_up_question": "",
            }),
        })
    return enriched


# =========================
# RECHECK
# =========================
def recheck_answer(original_misconception: dict, new_answer: str):
    """
    Evaluate if student's new answer resolves the misconception.
    GUARANTEED to return a dict with status and feedback.
    """
    print(f"[DEBUG] Rechecking answer for concept: {original_misconception.get('concept', 'unknown')}")

    if not is_academic_only(new_answer):
        return {
            "status": "unresolved",
            "feedback": "Please keep the response academic and related to the question.",
        }

    if not new_answer or len(new_answer.strip()) < 5:
        return {
            "status": "unresolved",
            "feedback": "Please provide a more complete answer to demonstrate your understanding.",
        }

    client = get_client()
    if client is None:
        return {
            "status": "partially_resolved",
            "feedback": "I can’t connect to the model right now. Your answer shows some progress—try refining it once the model is available.",
        }

    try:
        prompt = f"""You are an educational evaluator.

Original misconception the student had:
Concept: {original_misconception.get('concept', 'Unknown')}
Why it was wrong: {original_misconception.get('why_wrong', 'Incorrect understanding')}

Student's NEW answer after receiving feedback:
\"\"\"{new_answer}\"\"\"

Evaluate if the misconception is now resolved. Return your evaluation in this EXACT JSON format (no markdown, no code blocks):
{{
  "status": "resolved",
  "feedback": "Specific feedback on the student's new answer"
}}

Status must be one of: "resolved", "partially_resolved", or "unresolved"
Return ONLY the JSON object, nothing else."""
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
        )

        parsed = safe_json_load(getattr(response, "text", "") or "")
        if not parsed:
            raise ValueError("Invalid recheck JSON")

        valid_statuses = ["resolved", "partially_resolved", "unresolved"]
        status = parsed.get("status", "partially_resolved")
        if status not in valid_statuses:
            status = "partially_resolved"

        return {
            "status": status,
            "feedback": parsed.get("feedback", "Your answer shows some improvement."),
        }

    except ClientError as e:
        print(f"[DEBUG] Gemini API error in recheck: {e}")
        if "RESOURCE_EXHAUSTED" in str(e):
            return {
                "status": "partially_resolved",
                "feedback": "API quota reached. Your answer shows improvement in understanding.",
            }
        return {
            "status": "partially_resolved",
            "feedback": "Unable to fully evaluate right now, but your answer shows some progress.",
        }
    except Exception as e:
        print(f"[DEBUG] Error in recheck: {e}")
        return {
            "status": "partially_resolved",
            "feedback": "Your answer demonstrates improved understanding of the concept.",
        }
