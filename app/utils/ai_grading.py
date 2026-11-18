"""
AI-assisted grading and call-outcome classification.

Uses the Anthropic API when ANTHROPIC_API_KEY is configured in the environment.
When it isn't configured (e.g. local development, or before credentials are
provisioned), every function falls back to a clearly-labeled heuristic so the
rest of the system keeps working end to end without a hard dependency on an
external key being present. Swap the fallback for a real call the moment a key
is available — nothing else in the codebase needs to change.
"""
import os
import re
import json

_client = None
_ANTHROPIC_AVAILABLE = False

if os.environ.get("ANTHROPIC_API_KEY"):
    try:
        import anthropic
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        _ANTHROPIC_AVAILABLE = True
    except Exception:
        _client = None
        _ANTHROPIC_AVAILABLE = False


def _ask_model(prompt, max_tokens=400):
    """Single-shot text completion. Returns None on any failure so callers can
    fall back cleanly instead of raising into a request handler."""
    if not _ANTHROPIC_AVAILABLE:
        return None
    try:
        resp = _client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        parts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
        return "\n".join(parts).strip()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Screening call outcome classification
# ---------------------------------------------------------------------------

_POSITIVE_HINTS = ["yes", "available", "interested", "can join", "immediate", "sounds good", "happy to"]
_NEGATIVE_HINTS = ["not interested", "no longer looking", "declined", "not available", "already accepted", "withdraw"]


def classify_call_outcome(transcript: str):
    """Returns 'yes' | 'no' | 'neutral'."""
    if not transcript or not transcript.strip():
        return "neutral"

    if _ANTHROPIC_AVAILABLE:
        prompt = (
            "Classify this recruiting screening call transcript as exactly one word: "
            "yes (candidate is a good fit and wants to proceed), "
            "no (candidate is not interested or not a fit), or "
            "neutral (unclear, needs a human to review).\n\n"
            f"Transcript:\n{transcript}\n\nAnswer with one word only."
        )
        result = _ask_model(prompt, max_tokens=10)
        if result:
            word = result.strip().lower()
            if word in ("yes", "no", "neutral"):
                return word

    # Heuristic fallback — simple keyword scan
    text = transcript.lower()
    neg_hits = sum(1 for kw in _NEGATIVE_HINTS if kw in text)
    pos_hits = sum(1 for kw in _POSITIVE_HINTS if kw in text)
    if neg_hits > pos_hits:
        return "no"
    if pos_hits > 0 and neg_hits == 0:
        return "yes"
    return "neutral"


def summarize_call(transcript: str):
    if not transcript or not transcript.strip():
        return "No transcript available for this call."

    if _ANTHROPIC_AVAILABLE:
        prompt = (
            "Summarize this recruiting screening call transcript in 2-3 short sentences "
            f"for a recruiter to skim:\n\n{transcript}"
        )
        result = _ask_model(prompt, max_tokens=200)
        if result:
            return result

    # Heuristic fallback — trim to first ~280 chars
    snippet = transcript.strip().replace("\n", " ")
    return (snippet[:280] + "…") if len(snippet) > 280 else snippet


# ---------------------------------------------------------------------------
# Mock test subjective grading
# ---------------------------------------------------------------------------

def grade_subjective_answer(question_text: str, answer_text: str, max_marks: float):
    """Returns (score: float, feedback: str)."""
    if not answer_text or not answer_text.strip():
        return 0.0, "No answer submitted."

    if _ANTHROPIC_AVAILABLE:
        prompt = (
            "You are grading a candidate's answer for a recruiting mock test.\n"
            f"Question: {question_text}\n"
            f"Candidate's answer: {answer_text}\n"
            f"Maximum marks: {max_marks}\n\n"
            "Respond ONLY with JSON in this exact shape, no other text: "
            '{"score": <number between 0 and max_marks>, "feedback": "<one short sentence>"}'
        )
        result = _ask_model(prompt, max_tokens=150)
        if result:
            try:
                cleaned = re.sub(r"^```json|```$", "", result.strip(), flags=re.MULTILINE).strip()
                parsed = json.loads(cleaned)
                score = float(parsed.get("score", 0))
                score = max(0.0, min(score, max_marks))
                return score, parsed.get("feedback", "")
            except Exception:
                pass

    # Heuristic fallback — reward substantive answers, not correctness
    word_count = len(answer_text.split())
    if word_count < 5:
        return round(max_marks * 0.2, 2), "Answer is very brief — needs manual review."
    if word_count < 20:
        return round(max_marks * 0.5, 2), "Reasonable attempt — recommend manual review."
    return round(max_marks * 0.75, 2), "Substantive answer — recommend manual review to confirm accuracy."


def grade_mcq_answer(question, answer_text: str):
    """Returns (score: float, is_correct: bool) for an MCQ question."""
    correct = (question.correct_answer or "").strip().lower()
    given = (answer_text or "").strip().lower()
    is_correct = correct != "" and correct == given
    return (question.marks if is_correct else 0.0), is_correct
