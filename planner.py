from typing import Dict, Any, List
from llm_client import OllamaClient

# Choose your local model
OLLAMA_MODEL =  "gemma2:2b"

# HARD SKIP (deterministic) – never reply to these
SYSTEM_PHRASES = [
    "do not reply",
    "please do not reply",
    "system generated",
    "this is a system generated",
    "automated message",
    "no-reply",
    "noreply",
    "unsubscribe",
    "view in browser",
]

PROMO_PHRASES = [
    "register now",
    "enroll now",
    "limited time",
    "hurry",
    "offer",
    "discount",
    "webinar",
    "workshop",
    "promotion",
]

# Add domains you never want to reply to (banks, services, etc.)
BLOCKED_DOMAINS = {
    "icicibank.com",
    "custcomm.icicibank.com",
    "no-reply.hack2skill.com",
    "nptel.iitm.ac.in",
    "sendgrid.net",
}


def _domain(email_addr: str) -> str:
    if not email_addr or "@" not in email_addr:
        return ""
    return email_addr.split("@", 1)[1].lower().strip()


def _hard_skip(subject: str, body: str, from_email: str) -> str | None:
    text = f"{subject}\n{body}".lower()
    dom = _domain(from_email)

    if dom in BLOCKED_DOMAINS:
        return f"blocked_domain:{dom}"

    for p in SYSTEM_PHRASES:
        if p in text:
            return f"system_phrase:{p}"

    for p in PROMO_PHRASES:
        if p in text:
            return f"promo_phrase:{p}"

    # very common “mass mail” pattern
    if "dear customer" in text and ("team" in text or "sincerely" in text):
        return "mass_mail_pattern"

    return None


def classify(email: Dict[str, Any]) -> Dict[str, Any]:
    subject = email.get("subject") or ""
    body = email.get("body") or ""
    from_email = email.get("from_email") or ""

    reason = _hard_skip(subject, body, from_email)
    if reason:
        return {
            "category": "fyi",
            "urgency": "low",
            "reply_needed": False,
            "task_needed": False,
            "skip_reason": reason,
        }

    # If not hard-skipped, let AI decide
    return {
        "category": "ai",
        "urgency": "ai",
        "reply_needed": True,
        "task_needed": True,
        "skip_reason": None,
    }


def draft_reply(email: Dict[str, Any], cls: Dict[str, Any]) -> Dict[str, Any]:
    if cls.get("skip_reason"):
        return {"ai": None, "short": "", "detailed": "", "confidence": 0.0, "needs_review": False}

    client = OllamaClient(model=OLLAMA_MODEL)

    system = """
You are an email triage + reply assistant for a busy professional.
Return STRICT JSON only (no markdown, no extra text).

Be conservative:
- If it's a newsletter/promo/system/bank notice, set reply_needed=false and category="fyi".
- Do NOT invent facts. If needed info is missing, ask 1-3 crisp questions.

Schema:
{
  "category": "needs_reply" | "task_request" | "fyi" | "spam",
  "urgency": "low" | "medium" | "high",
  "reply_needed": true|false,
  "action_items": [{"title": "...", "priority": "low|medium|high", "next_step": "..."}],
  "draft_short": "string",
  "draft_detailed": "string",
  "confidence": 0.0-1.0,
  "why": "short reason"
}
""".strip()

    user = f"""
EMAIL
From: {email.get("from_name") or ""} <{email.get("from_email") or ""}>
Subject: {email.get("subject") or ""}
Received: {email.get("received_at") or ""}

Body (clean text):
{(email.get("body") or "")[:2500]}

TASK
1) Decide category + urgency + reply_needed.
2) Extract action items (max 5).
3) If reply_needed=true, draft:
   - draft_short (2-4 lines)
   - draft_detailed (6-12 lines, bullets if useful)
Sign as: Yachit
""".strip()

    ai = client.chat_json(system=system, user=user, temperature=0.2, timeout=120)

    reply_needed = bool(ai.get("reply_needed", False))
    confidence = float(ai.get("confidence", 0.5))
    needs_review = confidence < 0.75

    short = ai.get("draft_short", "") if reply_needed else ""
    detailed = ai.get("draft_detailed", "") if reply_needed else ""

    return {
        "ai": ai,
        "short": short,
        "detailed": detailed,
        "confidence": confidence,
        "needs_review": needs_review,
    }