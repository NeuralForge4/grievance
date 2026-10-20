"""Mail collector: reads UNSEEN mail from an IMAP mailbox and sends each email to the prioritiser.
Env: IMAP_HOST, IMAP_USER, IMAP_PASS (use an app password), IMAP_FOLDER=INBOX, POLL_SECONDS=60.
Run:  python -m gai.collector"""
import os, re, time, email, imaplib
from email import policy
from email.utils import parsedate_to_datetime, parseaddr
GOV = re.compile(r"@([\w-]+\.)*(gov|nic)\.in$", re.I)

def parse_message(raw: bytes) -> dict:
    m = email.message_from_bytes(raw, policy=policy.default)
    part = m.get_body(preferencelist=("plain", "html"))
    body = part.get_content() if part else ""
    if part and part.get_content_type() == "text/html": body = re.sub(r"<style[\s\S]*?</style>|<[^>]+>", " ", body); body = re.sub(r"\s+", " ", body)
    try: when = parsedate_to_datetime(m["date"]).isoformat(timespec="seconds")
    except Exception: when = None
    frm = str(m["from"] or "Unknown")
    return dict(sender=frm, subject=str(m["subject"] or "(no subject)"), body=body.strip(), received_at=when, gid=str(m["message-id"] or ""),
                sender_type="official" if GOV.search(parseaddr(frm)[1]) else "citizen")

def poll_once(app, host, user, pw, folder="INBOX"):
    n = 0
    with imaplib.IMAP4_SSL(host) as im, app.app_context():
        im.login(user, pw); im.select(folder)
        _, ids = im.search(None, "UNSEEN")
        for num in ids[0].split():
            _, d = im.fetch(num, "(RFC822)")
            if app.ingest(**parse_message(d[0][1])): n += 1
    return n

if __name__ == "__main__":
    from .app import create_app
    app = create_app()
    while True:
        try: print("ingested", poll_once(app, os.environ["IMAP_HOST"], os.environ["IMAP_USER"], os.environ["IMAP_PASS"], os.environ.get("IMAP_FOLDER", "INBOX")))
        except Exception as e: print("collector error:", e)
        time.sleep(int(os.environ.get("POLL_SECONDS", 60)))
