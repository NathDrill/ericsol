import smtplib
from email.message import EmailMessage
from ..core.config import settings


def send_mail(subject: str, body: str, recipients: list[str]):
    if not settings.smtp_host or not recipients:
        return False
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = ", ".join(recipients)
    msg.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as s:
        if settings.smtp_user and settings.smtp_pass:
            s.starttls()
            s.login(settings.smtp_user, settings.smtp_pass)
        s.send_message(msg)
    return True

