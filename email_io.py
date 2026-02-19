import imaplib
import smtplib
import ssl
import email
from email.message import EmailMessage
from email.header import decode_header
from email.utils import parseaddr, parsedate_to_datetime
from typing import List, Dict, Any, Optional
import re


def _decode_mime_words(s: str) -> str:
    parts = decode_header(s)
    out = ""
    for text, enc in parts:
        if isinstance(text, bytes):
            out += text.decode(enc or "utf-8", errors="replace")
        else:
            out += text
    return out


def imap_connect(imap_host: str, gmail_address: str, app_password: str):
    mail = imaplib.IMAP4_SSL(imap_host)
    mail.login(gmail_address, app_password)
    return mail


def html_to_text(html: str) -> str:
    # Remove scripts/styles
    html = re.sub(r"(?is)<(script|style).*?>.*?</\1>", "", html)

    # Replace common block tags with newline
    html = re.sub(r"(?i)<br\s*/?>", "\n", html)
    html = re.sub(r"(?i)</p\s*>", "\n", html)
    html = re.sub(r"(?i)</div\s*>", "\n", html)

    # Remove all tags
    html = re.sub(r"(?s)<.*?>", " ", html)

    # Clean entities
    html = html.replace("&nbsp;", " ")
    html = html.replace("&amp;", "&")
    html = html.replace("&lt;", "<")
    html = html.replace("&gt;", ">")

    # Normalize whitespace
    html = re.sub(r"\s+", " ", html)

    return html.strip()


def extract_body(msg) -> str:
    """
    FORCE clean HTML emails.
    """
    if msg.is_multipart():
        html_content = None
        text_content = None

        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")

            if "attachment" in disp.lower():
                continue

            payload = part.get_payload(decode=True)
            if not payload:
                continue

            charset = part.get_content_charset() or "utf-8"
            decoded = payload.decode(charset, errors="replace")

            if ctype == "text/html":
                html_content = decoded
            elif ctype == "text/plain":
                text_content = decoded

        if html_content:
            return html_to_text(html_content)

        if text_content:
            return text_content.strip()

        return ""

    else:
        payload = msg.get_payload(decode=True)
        if not payload:
            return ""

        charset = msg.get_content_charset() or "utf-8"
        decoded = payload.decode(charset, errors="replace")

        # If it's HTML, convert it
        if "<html" in decoded.lower() or "<p>" in decoded.lower():
            return html_to_text(decoded)

        return decoded.strip()


def fetch_unread_emails(mail, max_results: int = 5) -> List[Dict[str, Any]]:
    mail.select("INBOX")
    status, data = mail.search(None, "UNSEEN")
    if status != "OK":
        return []

    ids = data[0].split()
    ids = ids[-max_results:]

    results = []
    for eid in ids:
        status, msg_data = mail.fetch(eid, "(RFC822)")
        if status != "OK":
            continue

        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw)

        subject = _decode_mime_words(msg.get("Subject", "(no subject)"))
        from_raw = msg.get("From", "")
        from_name, from_email = parseaddr(from_raw)
        from_name = _decode_mime_words(from_name) if from_name else ""

        date_raw = msg.get("Date", "")
        try:
            received_at = parsedate_to_datetime(date_raw).isoformat()
        except Exception:
            received_at = date_raw or "unknown"

        body_text = extract_body(msg)

        results.append(
            {
                "imap_id": eid.decode() if isinstance(eid, bytes) else str(eid),
                "from_name": from_name,
                "from_email": from_email,
                "subject": subject,
                "received_at": received_at,
                "body": body_text,
                "message_id": msg.get("Message-ID"),
                "references": msg.get("References"),
            }
        )

    return results


def smtp_send(
    smtp_host: str,
    smtp_port: int,
    gmail_address: str,
    app_password: str,
    to_email: str,
    subject: str,
    body: str,
    message_id: Optional[str] = None,
    references: Optional[str] = None,
):
    msg = EmailMessage()
    msg["From"] = gmail_address
    msg["To"] = to_email
    msg["Subject"] = subject

    if message_id:
        msg["In-Reply-To"] = message_id
    if references:
        msg["References"] = references

    msg.set_content(body)

    context = ssl.create_default_context()
    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls(context=context)
        server.login(gmail_address, app_password)
        server.send_message(msg)