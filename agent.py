import os
from dotenv import load_dotenv

from email_io import imap_connect, fetch_unread_emails, smtp_send
from planner import classify, draft_reply


def main():
    load_dotenv()

    gmail = os.getenv("GMAIL_ADDRESS", "").strip()
    app_pass = os.getenv("GMAIL_APP_PASSWORD", "").strip()
    imap_host = os.getenv("IMAP_HOST", "imap.gmail.com").strip()
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587"))

    if not gmail or not app_pass:
        print("❌ Missing GMAIL_ADDRESS or GMAIL_APP_PASSWORD in .env")
        return

    mail = imap_connect(imap_host, gmail, app_pass)
    emails = fetch_unread_emails(mail, max_results=5)

    if not emails:
        print("✅ No unread emails found.")
        mail.logout()
        return

    for i, e in enumerate(emails, start=1):
        print("\n" + "=" * 90)
        print(f"[{i}] From: {e['from_email']}  | Subject: {e['subject']}")
        print(f"Received: {e['received_at']}")
        print("-" * 90)

        preview = e["body"][:700] + ("…" if len(e["body"]) > 700 else "")
        print(preview or "(No body text found)")

        cls = classify(e)
        if cls.get("skip_reason"):
            print("\n--- Decision ---")
            print(f"⏭️ Auto-skip: {cls['skip_reason']}")
            continue

        out = draft_reply(e, cls)
        ai = out.get("ai") or {}

        print("\n--- AI Decision ---")
        print({
            "category": ai.get("category"),
            "urgency": ai.get("urgency"),
            "reply_needed": ai.get("reply_needed"),
            "confidence": ai.get("confidence"),
            "why": ai.get("why"),
        })

        action_items = ai.get("action_items") or []
        print("\n--- AI Action Items ---")
        if action_items:
            for t in action_items:
                print(f"- [{t.get('priority','medium')}] {t.get('title')} | next: {t.get('next_step')}")
        else:
            print("- None")

        if not ai.get("reply_needed"):
            print("\n⏭️ No reply needed.")
            continue

        print("\n--- Draft (SHORT) ---\n")
        print(out["short"])

        print("\n--- Draft (DETAILED) ---\n")
        print(out["detailed"])

        if out.get("needs_review"):
            print("\n⚠️ Low confidence → recommend SKIP unless you review carefully.")

        choice = input("Type APPROVE to send SHORT, DETAILED to send detailed, or SKIP: ").strip().upper()

        if choice == "APPROVE":
            smtp_send(
                smtp_host=smtp_host,
                smtp_port=smtp_port,
                gmail_address=gmail,
                app_password=app_pass,
                to_email=e["from_email"],
                subject="Re: " + e["subject"],
                body=out["short"],
                message_id=e.get("message_id"),
                references=e.get("references"),
            )
            print("✅ Sent SHORT reply (threaded).")

        elif choice == "DETAILED":
            smtp_send(
                smtp_host=smtp_host,
                smtp_port=smtp_port,
                gmail_address=gmail,
                app_password=app_pass,
                to_email=e["from_email"],
                subject="Re: " + e["subject"],
                body=out["detailed"],
                message_id=e.get("message_id"),
                references=e.get("references"),
            )
            print("✅ Sent DETAILED reply (threaded).")

        else:
            print("⏭️ Skipped.")

    mail.logout()


if __name__ == "__main__":
    main()