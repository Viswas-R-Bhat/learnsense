import streamlit as st
import uuid
from backend import full_analysis, recheck_answer, generate_questions_from_notes

st.set_page_config(page_title="LearnSense", page_icon="🧠", layout="wide")

# ---------- CSS (ChatGPT-ish) ----------
st.markdown(
    """
    <style>
      /* Constrain Streamlit main content width safely */
      section.main > div { max-width: 900px; margin: 0 auto; }

      /* Sidebar like ChatGPT left rail */
      [data-testid="stSidebar"] { min-width: 320px; max-width: 320px; }
      [data-testid="stSidebar"] .stMarkdown { font-size: 0.95rem; }

      /* Tighten chat spacing */
      [data-testid="stChatMessage"] { padding-top: 6px; padding-bottom: 6px; }

      /* Input rounded */
      [data-testid="stChatInput"] textarea { border-radius: 14px !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------- Session State ----------
if "user_id" not in st.session_state:
    st.session_state.user_id = str(uuid.uuid4())

if "messages" not in st.session_state:
    st.session_state.messages = []

if "last_misconception" not in st.session_state:
    st.session_state.last_misconception = None
if "last_misconception_key" not in st.session_state:
    st.session_state.last_misconception_key = None

if "mode" not in st.session_state:
    st.session_state.mode = "analyze"  # analyze | recheck

if "attempts_by_key" not in st.session_state:
    st.session_state.attempts_by_key = {}

if "pending" not in st.session_state:
    st.session_state.pending = False
if "pending_mode" not in st.session_state:
    st.session_state.pending_mode = "analyze"
if "pending_input" not in st.session_state:
    st.session_state.pending_input = ""
if "pending_placeholder_index" not in st.session_state:
    st.session_state.pending_placeholder_index = None
if "pending_request_id" not in st.session_state:
    st.session_state.pending_request_id = None

if "cancel_requested" not in st.session_state:
    st.session_state.cancel_requested = False
if "cancel_request_id" not in st.session_state:
    st.session_state.cancel_request_id = None

# Tutor settings (left rail)
if "learning_mode" not in st.session_state:
    st.session_state.learning_mode = "Exam"  # ELI5 | Exam | Interview
if "current_topic" not in st.session_state:
    st.session_state.current_topic = "General"
if "current_question" not in st.session_state:
    st.session_state.current_question = ""

# Notes -> question bank
if "question_bank" not in st.session_state:
    st.session_state.question_bank = []

# Attachment state (ChatGPT-like "+")
if "uploaded_image_bytes" not in st.session_state:
    st.session_state.uploaded_image_bytes = None
if "uploaded_image_mime" not in st.session_state:
    st.session_state.uploaded_image_mime = None

# Debounce
if "last_user_text" not in st.session_state:
    st.session_state.last_user_text = None


# ---------- Helpers ----------
def add_msg(role: str, content: str):
    st.session_state.messages.append({"role": role, "content": content})


def render_msg(role: str, content: str):
    with st.chat_message(role):
        st.markdown(content)


def misconception_key(m: dict):
    concept = (m or {}).get("concept", "") or ""
    why_wrong = (m or {}).get("why_wrong", "") or ""
    return f"{concept}::{why_wrong[:80]}"


def is_give_up(text: str):
    t = (text or "").strip().lower()
    phrases = ["i give up", "give up", "show answer", "answer please"]
    return any(p in t for p in phrases)


def _limit_sentences(text: str, max_sentences: int = 3, min_sentences: int = 2):
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


def final_answer_for(m: dict):
    if not m:
        return "Here is the correct idea in brief. Focus on the defining property and how it applies."
    final_answer = m.get("final_answer", "") or ""
    if final_answer.strip():
        return _limit_sentences(final_answer)
    hint = m.get("hint", "") or ""
    why_wrong = m.get("why_wrong", "") or ""
    parts = []
    if hint:
        parts.append(f"Key idea: {hint.strip()}")
    if why_wrong:
        parts.append(why_wrong.strip())
    return _limit_sentences(" ".join(parts))


def format_tutor_message(concept: str, why_wrong: str, hint: str, diagnostic: str,
                         explanation: str, example: str, follow_up: str) -> str:
    parts = []
    if concept:
        parts.append(f"### What’s going wrong\nIt looks like the confusion is about **{concept}**.")
    if why_wrong:
        parts.append(f"**Why this isn’t correct yet:** {why_wrong}")
    if hint:
        parts.append(f"### Hint\n{hint}")
    if diagnostic:
        parts.append(f"### Quick check\n{diagnostic}")
    if explanation:
        parts.append(f"### Explanation\n{explanation}")
    if example:
        parts.append(f"### Example\n{example}")
    if follow_up:
        parts.append(f"### Try again\n{follow_up}")
    else:
        parts.append("### Try again\nExplain it again in your own words.")
    return "\n\n".join([p for p in parts if p])


def reveal_answer_and_reset(prefix: str = "Got it — here’s the correct answer"):
    m = st.session_state.last_misconception
    if not m:
        add_msg("assistant", "Share your answer and I’ll help.")
        st.session_state.mode = "analyze"
        return

    final_answer = final_answer_for(m)
    assistant_text = (
        f"### {prefix}\n\n"
        f"{final_answer}\n\n"
        "If you want, send another answer to analyze."
    )
    add_msg("assistant", assistant_text)

    key = st.session_state.last_misconception_key
    if key:
        st.session_state.attempts_by_key.pop(key, None)

    st.session_state.last_misconception = None
    st.session_state.last_misconception_key = None
    st.session_state.mode = "analyze"


def is_academic_query(text: str) -> bool:
    t = (text or "").lower()
    banned = [
        "game", "minecraft", "roblox", "valorant", "fortnite",
        "roleplay", "story", "fanfic", "meme", "joke",
        "dating", "pickup", "flirt", "bgmi", "efootball", "gta",
        "hack", "cheat code", "aimbot",
    ]
    return not any(b in t for b in banned)


def reset_all():
    st.session_state.messages = []
    st.session_state.last_misconception = None
    st.session_state.last_misconception_key = None
    st.session_state.mode = "analyze"
    st.session_state.pending = False
    st.session_state.pending_mode = "analyze"
    st.session_state.pending_input = ""
    st.session_state.pending_placeholder_index = None
    st.session_state.pending_request_id = None
    st.session_state.cancel_requested = False
    st.session_state.cancel_request_id = None
    st.session_state.attempts_by_key = {}
    st.session_state.last_user_text = None
    st.session_state.uploaded_image_bytes = None
    st.session_state.uploaded_image_mime = None
    st.rerun()


# ==========================
# LEFT RAIL (ChatGPT-like)
# ==========================
with st.sidebar:
    st.markdown("## LearnSense")
    st.caption("Understand your mistakes, not just your marks")

    st.session_state.learning_mode = st.selectbox(
        "Mode",
        ["ELI5", "Exam", "Interview"],
        index=["ELI5", "Exam", "Interview"].index(st.session_state.learning_mode),
        help="Like ChatGPT model picker — changes tutoring style.",
    )

    st.session_state.current_topic = st.selectbox(
        "Topic",
        ["General", "DSA", "Math", "OS", "DBMS", "CN", "AI/ML", "Physics", "Chemistry", "Biology", "Economics", "Other"],
        index=["General", "DSA", "Math", "OS", "DBMS", "CN", "AI/ML", "Physics", "Chemistry", "Biology", "Economics", "Other"].index(st.session_state.current_topic),
    )

    st.session_state.current_question = st.text_area(
        "Question (required)",
        value=st.session_state.current_question,
        height=80,
        placeholder="E.g., Differentiate AVL and BST.",
    )

    st.markdown("---")

    with st.expander("📄 Generate practice questions from notes"):
        notes_text = st.text_area(
            "Paste notes",
            height=160,
            placeholder="Paste your class notes/key points here..."
        )

        gen = st.button("Generate", use_container_width=True)

        if gen and notes_text.strip():
            qb = generate_questions_from_notes(
                notes_text=notes_text,
                topic=st.session_state.current_topic,
                mode=st.session_state.learning_mode
            )

            if isinstance(qb, dict) and qb.get("questions"):
                st.session_state.question_bank = qb["questions"]
            elif isinstance(qb, list):
                st.session_state.question_bank = qb
            else:
                st.session_state.question_bank = []

            if st.session_state.question_bank:
                st.success(f"Generated {len(st.session_state.question_bank)} questions.")
            else:
                st.warning("Couldn’t generate questions. Try shorter notes or clearer points.")

        if st.session_state.question_bank:
            choices = [
                f"{i+1}. ({q.get('difficulty','?')}, {q.get('type','?')}) {q.get('q','')[:90]}"
                for i, q in enumerate(st.session_state.question_bank)
            ]
            idx = st.selectbox(
                "Pick a question",
                range(len(choices)),
                format_func=lambda i: choices[i]
            )

            if st.button("Use selected question", use_container_width=True):
                selected = st.session_state.question_bank[idx]
                st.session_state.current_question = selected.get("q", "")
                st.session_state.current_topic = selected.get("topic", st.session_state.current_topic)
                st.session_state.mode = "analyze"
                st.session_state.uploaded_image_bytes = None
                st.session_state.uploaded_image_mime = None
                st.rerun()

    st.markdown("---")
    if st.button("🔄 Reset chat", use_container_width=True):
        reset_all()


# ==========================
# MAIN CHAT
# ==========================
if len(st.session_state.messages) == 0:
    add_msg("assistant", "Hi! Type an answer below and I’ll analyze it for misconceptions.")

for msg in st.session_state.messages:
    render_msg(msg["role"], msg["content"])

# Recheck controls
if (
    st.session_state.mode == "recheck"
    and st.session_state.last_misconception
    and not st.session_state.pending
):
    key = st.session_state.last_misconception_key or "current"
    attempts = st.session_state.attempts_by_key.get(key, 0)
    remaining = max(0, 3 - attempts)
    c1, c2 = st.columns([3, 1])
    with c1:
        st.caption(f"Attempts left: {remaining}")
    with c2:
        if st.button("🏳️ Give up"):
            reveal_answer_and_reset("No worries — here’s the correct answer")
            st.rerun()

# Stop generating
if st.session_state.pending:
    if st.button("⏹ Stop generating"):
        st.session_state.cancel_requested = True
        st.session_state.cancel_request_id = st.session_state.pending_request_id
        idx = st.session_state.pending_placeholder_index
        if idx is not None and 0 <= idx < len(st.session_state.messages):
            st.session_state.messages[idx]["content"] = "⏹ Stopped."
        st.session_state.pending = False
        st.session_state.pending_input = ""
        st.session_state.pending_placeholder_index = None
        st.session_state.pending_request_id = None
        st.rerun()

# Resolve pending
if st.session_state.pending:
    if st.session_state.cancel_requested and st.session_state.cancel_request_id == st.session_state.pending_request_id:
        st.session_state.pending = False
        st.session_state.pending_input = ""
        st.session_state.pending_placeholder_index = None
        st.session_state.pending_request_id = None
        st.session_state.cancel_requested = False
        st.session_state.cancel_request_id = None
        st.rerun()

    request_id = st.session_state.pending_request_id

    with st.spinner("Analyzing with Gemini…"):
        assistant_text = "I couldn’t analyze that yet. Try again."
        try:
            if st.session_state.pending_mode == "recheck":
                res = recheck_answer(
                    st.session_state.last_misconception,
                    st.session_state.pending_input
                )
                status = res.get("status", "partially_resolved")
                feedback = (res.get("feedback", "") or "").strip()

                key = st.session_state.last_misconception_key or "current"
                attempts = st.session_state.attempts_by_key.get(key, 0)

                if status == "resolved":
                    assistant_text = f"Nice — that clears it up.\n\n{feedback}\n\nWant another answer checked?"
                    st.session_state.attempts_by_key.pop(key, None)
                    st.session_state.last_misconception = None
                    st.session_state.last_misconception_key = None
                    st.session_state.mode = "analyze"
                else:
                    attempts += 1
                    st.session_state.attempts_by_key[key] = attempts
                    if attempts >= 3:
                        reveal_answer_and_reset("No worries — here’s the correct answer")
                        assistant_text = "✅ Answer revealed above."
                        st.session_state.mode = "analyze"
                    else:
                        lead = "Not quite yet." if status == "unresolved" else "You're close."
                        remaining = max(0, 3 - attempts)

                        hints = (st.session_state.last_misconception or {}).get("hints", []) or []
                        hint_line = ""
                        if hints:
                            idx_hint = min(len(hints) - 1, attempts - 1)
                            hint_line = f"\n\n### Hint\n{hints[idx_hint]}"

                        assistant_text = (
                            f"### {lead}\n\n"
                            f"{feedback}"
                            f"{hint_line}\n\n"
                            f"**Attempts left:** {remaining}\n\n"
                            "### Try again\n"
                            "Answer again in your own words."
                        )
                        st.session_state.mode = "recheck"

            else:
                results = full_analysis(
                    student_input=st.session_state.pending_input,
                    user_id=st.session_state.user_id,
                    question=st.session_state.current_question,
                    mode=st.session_state.learning_mode,
                    topic=st.session_state.current_topic,
                    image_bytes=st.session_state.uploaded_image_bytes,
                    image_mime=st.session_state.uploaded_image_mime,
                )

                if isinstance(results, dict) and results.get("error"):
                    assistant_text = results.get("error_message", "Please try again.")
                    st.session_state.last_misconception = None
                    st.session_state.last_misconception_key = None
                    st.session_state.mode = "analyze"
                elif not results:
                    assistant_text = "I couldn’t analyze that yet. Try a more complete answer."
                    st.session_state.last_misconception = None
                    st.session_state.last_misconception_key = None
                    st.session_state.mode = "analyze"
                else:
                    item = results[0]
                    meta = item.get("meta", {})
                    m = item["misconception"]
                    t = item["teaching"]

                    is_correct = meta.get("is_correct", False) or m.get("concept") == "No misconception"
                    concept = m.get("concept", "this concept")

                    if is_correct:
                        parts = [
                            "Nice work — I think you’ve got it.",
                            (t.get("explanation", "") or "").strip(),
                            "If you want, send another answer to analyze."
                        ]
                        assistant_text = "\n\n".join([p for p in parts if p])
                        st.session_state.last_misconception = None
                        st.session_state.last_misconception_key = None
                        st.session_state.mode = "analyze"
                    else:
                        assistant_text = format_tutor_message(
                            concept=concept,
                            why_wrong=(m.get("why_wrong", "") or "").strip(),
                            hint=(m.get("hint", "") or "").strip(),
                            diagnostic=(m.get("diagnostic_question", "") or "").strip(),
                            explanation=(t.get("explanation", "") or "").strip(),
                            example=(t.get("analogy", "") or "").strip(),
                            follow_up=(t.get("follow_up_question", "") or "").strip(),
                        )

                        st.session_state.last_misconception = m
                        k = misconception_key(m)
                        st.session_state.last_misconception_key = k
                        st.session_state.attempts_by_key[k] = 0
                        st.session_state.mode = "recheck"

                # Clear attachment after send (ChatGPT-like)
                st.session_state.uploaded_image_bytes = None
                st.session_state.uploaded_image_mime = None

        except Exception:
            assistant_text = "I couldn’t reach the model right now (it may be overloaded). Please try again in a moment."
            st.session_state.last_misconception = None
            st.session_state.last_misconception_key = None
            st.session_state.mode = "analyze"

        idx = st.session_state.pending_placeholder_index
        canceled = (st.session_state.cancel_requested and st.session_state.cancel_request_id == request_id)
        if not canceled and idx is not None and 0 <= idx < len(st.session_state.messages):
            st.session_state.messages[idx]["content"] = assistant_text

        # cleanup
        st.session_state.pending = False
        st.session_state.pending_input = ""
        st.session_state.pending_placeholder_index = None
        st.session_state.pending_request_id = None
        if st.session_state.cancel_request_id == request_id:
            st.session_state.cancel_requested = False
            st.session_state.cancel_request_id = None

    st.rerun()


# ==========================
# INPUT BAR + ATTACHMENT ("+")
# ==========================
attach_col, rest_col = st.columns([1, 12])

with attach_col:
    # Streamlit popover behaves like a ChatGPT "+" menu
    try:
        with st.popover("➕", help="Attach an image (handwritten answer, diagram, notes)"):
            up = st.file_uploader(
                "Attach image",
                type=["png", "jpg", "jpeg"],
                accept_multiple_files=False,
                label_visibility="collapsed",
            )
            if up is not None:
                st.session_state.uploaded_image_bytes = up.read()
                st.session_state.uploaded_image_mime = up.type
                st.success("Attached. Now send your answer.")
    except Exception:
        with st.expander("➕ Attach image"):
            up = st.file_uploader(
                "Attach image",
                type=["png", "jpg", "jpeg"],
                accept_multiple_files=False,
            )
            if up is not None:
                st.session_state.uploaded_image_bytes = up.read()
                st.session_state.uploaded_image_mime = up.type
                st.success("Attached. Now send your answer.")

with rest_col:
    if st.session_state.uploaded_image_bytes:
        st.caption("📎 Image attached")

placeholder = "Type your answer…" if st.session_state.mode == "analyze" else "Try again (I’ll recheck)…"
user_text = st.chat_input(placeholder, disabled=st.session_state.pending)

# Debounce identical immediate resubmits
if user_text:
    if user_text == st.session_state.last_user_text:
        st.stop()
    st.session_state.last_user_text = user_text

if user_text and not st.session_state.pending:
    add_msg("user", user_text)

    # Academic-only guardrail
    if not is_academic_query(user_text) or not is_academic_query(st.session_state.current_question):
        add_msg("assistant", "I can help only with academic/learning questions. Please ask something educational (concepts, problems, explanations).")
        st.rerun()

    # Require question
    if st.session_state.mode == "analyze" and not st.session_state.current_question.strip():
        add_msg("assistant", "Please enter the **Question** in the left panel first, then type your answer.")
        st.rerun()

    # Give up shortcut
    if is_give_up(user_text):
        if st.session_state.mode == "recheck" and st.session_state.last_misconception:
            reveal_answer_and_reset()
            st.rerun()
        else:
            add_msg("assistant", "Share your answer and I’ll help.")
            st.rerun()

    # Start analysis
    add_msg("assistant", "⏳ Analyzing…")
    st.session_state.pending_placeholder_index = len(st.session_state.messages) - 1
    st.session_state.pending_input = user_text
    st.session_state.pending_mode = st.session_state.mode
    st.session_state.pending = True
    st.session_state.pending_request_id = str(uuid.uuid4())
    st.session_state.cancel_requested = False
    st.session_state.cancel_request_id = None
    st.rerun()
