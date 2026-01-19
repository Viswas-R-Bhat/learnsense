# LearnSense 🧠

LearnSense is an adaptive AI tutor built with the Gemini 3 API that helps students understand **why they are wrong**, not just whether they are wrong.

## What it does
- Diagnoses student mistakes from text or handwritten images
- Identifies the first incorrect reasoning step (Mistake Microscope)
- Guides learning using a multi-level Socratic hint ladder
- Reveals full solutions with grading rubrics on give-up
- Builds a personal concept mastery graph over time

## Gemini 3 Integration
LearnSense uses the Gemini 3 family for:
- Multimodal reasoning over handwritten student answers
- Structured reasoning to extract solution steps and misconceptions
- Low-latency Socratic tutoring loops
- Generating grading rubrics and minimal fixes for answers

Gemini 3 is central to the system’s ability to reason over student thinking, not just generate answers.

## How to run
```bash
pip install -r requirements.txt
streamlit run ui.py
