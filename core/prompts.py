def prompt_diagnose(question: str, student_text: str, memory_block: str, mode: str, topic: str) -> str:
    return f"""
You are an educational tutor. Only academic/learning content.

Tutor style: {mode}
Topic: {topic}

Task:
1) Evaluate the student's answer to the Question (use the image if provided).
2) Extract the student's solution into ordered steps (strings).
3) Identify the first incorrect step index (0-based). If fully correct, wrong_step_index=-1.
4) Provide a short fix sentence for the wrong step (or reinforcement if correct).
5) If correct: is_correct=true and return ONE item with concept="No misconception".
6) If incorrect: return 1-3 misconceptions with teaching + 3-step hint ladder.
7) Return ONLY valid JSON (no markdown).

Question:
\"\"\"{question}\"\"\"

Student answer (typed):
\"\"\"{student_text}\"\"\"

Student history:
{memory_block}

Return JSON:
{{
  "is_correct": true|false,
  "confidence": 0.0,
  "steps": ["..."],
  "wrong_step_index": -1,
  "fix": "",
  "misconceptions": [
    {{
      "concept": "",
      "why_wrong": "",
      "hints": ["", "", ""],
      "diagnostic_question": "",
      "severity": "low|medium|high",
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

def prompt_socratic(question: str, student_text: str, memory_block: str, hint_level: int, mode: str, topic: str) -> str:
    return f"""
You are an educational tutor. Only academic/learning content.

Goal: Continue tutoring with a Socratic approach.

Rules:
- If hint_level < 4: do NOT give the final solution.
- Choose exactly one best next question to ask now.
- Provide a 3-step hint ladder (subtle -> explicit).
- If hint_level == 4: provide the full correct answer briefly.

Question:
\"\"\"{question}\"\"\"

Student response:
\"\"\"{student_text}\"\"\"

Student history:
{memory_block}

hint_level: {hint_level}

Return ONLY JSON:
{{
  "is_correct": true|false,
  "confidence": 0.0,
  "next_question": "",
  "misconceptions": [
    {{
      "concept": "",
      "why_wrong": "",
      "hints": ["", "", ""],
      "diagnostic_question": "",
      "severity": "low|medium|high",
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

def prompt_rubric(question: str, student_attempt: str, topic: str, mode: str) -> str:
    return f"""
IMPORTANT: You MUST return valid JSON. Do NOT include explanations outside JSON.

You are an educational tutor. Only academic/learning content.

The student gave up (or needs the full answer).
1) Provide step-by-step solution_steps.
2) Provide a grading rubric with marks per step.
3) Provide minimal_fix: smallest changes needed to correct the student's attempt.
4) Provide final_answer (concise).

Question:
\"\"\"{question}\"\"\"

Student attempt:
\"\"\"{student_attempt}\"\"\"

Return ONLY JSON:
{{
  "solution_steps": ["..."],
  "rubric": [
    {{
      "step": "",
      "marks": 1,
      "expected": "",
      "common_errors": "",
      "student_error": ""
    }}
  ],
  "minimal_fix": "",
  "final_answer": ""
}}
""".strip()

def prompt_generate_exam(topic: str, style: str, n: int) -> str:
    return f"""
You are an exam setter. Only academic content.

Create {n} exam questions for topic: {topic}.
Style: {style}

Return ONLY JSON:
{{
  "questions": [
    {{
      "q": "",
      "difficulty": "easy|medium|hard",
      "type": "concept|application|trap"
    }}
  ]
}}
""".strip()

def prompt_exam_report(topic: str, qa_pairs_text: str) -> str:
    return f"""
You are an educational examiner. Only academic content.

Given the student's exam responses, produce:
- summary (short)
- score_estimate (0-100)
- weakest_concepts (top 3)
- next_steps (3 bullets)

Exam topic: {topic}

Q/A pairs:
{qa_pairs_text}

Return ONLY JSON:
{{
  "summary": "",
  "score_estimate": 0,
  "weakest_concepts": ["", "", ""],
  "next_steps": ["", "", ""]
}}
""".strip()
