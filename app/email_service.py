import logging
import secrets
import smtplib
import ssl
import string
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from fastapi import HTTPException

from app.config import GMAIL_ADDRESS, GMAIL_APP_PASSWORD, GMAIL_FROM_ADDRESS

logger = logging.getLogger(__name__)


def generate_verification_code() -> str:
    """A 6-digit numeric code, not a URL token - shared by both the staff
    and client-portal forgot-password flows (see app/auth/service.py,
    app/client_auth/service.py) so someone reading a code off their phone/
    email has something short enough to type by hand, unlike the
    opaque-token links used elsewhere (invite links, shared-document
    links)."""
    return "".join(secrets.choice(string.digits) for _ in range(6))

# Gmail's own SMTP relay, authenticated with an App Password (not the real
# account password - Gmail requires 2-Step Verification to be on before it
# will even issue one). No transactional-email provider (SendGrid/SES/etc)
# is set up for this app, and this is the same "reuse an ordinary account,
# no new paid service" approach the rest of the app takes for outbound
# communication (see utils/shareToWhatsApp.ts - wa.me, not a WhatsApp
# Business API account).
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
# Never block a worker indefinitely on a slow or unreachable mail server.
SMTP_TIMEOUT_SECONDS = 15


def _smtp_login(server: smtplib.SMTP) -> None:
    """STARTTLS with a *verifying* TLS context, then log in. smtplib's
    default context for starttls() does not validate the server's
    certificate, which would let a network attacker read the credentials
    and every verification code - the explicit default context checks the
    certificate chain and hostname."""
    server.starttls(context=ssl.create_default_context())
    server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD.get_secret_value())


def check_credentials() -> None:
    """Logs in to the SMTP server without sending anything - used by
    scripts/check_email_credentials.py to confirm a rotated password works.
    Raises on any problem."""
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        raise RuntimeError("GMAIL_ADDRESS / GMAIL_APP_PASSWORD are not configured")
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS) as server:
        _smtp_login(server)


def send_email(to_email: str, subject: str, body_text: str) -> None:
    """Sends a plain-text email via Gmail SMTP. Raises HTTPException(500)
    with a clear, non-leaky message if email isn't configured or sending
    fails - callers (the forgot-password endpoints) let this propagate
    rather than silently pretending an email went out."""
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        raise HTTPException(
            status_code=500,
            detail="Email sending isn't configured on this server yet.",
        )

    message = MIMEMultipart()
    # Visible sender can be a "+" alias of the authenticated account (see
    # GMAIL_FROM_ADDRESS in app/config.py) - login/auth below always uses
    # the real account either way.
    message["From"] = GMAIL_FROM_ADDRESS
    message["To"] = to_email
    message["Subject"] = subject
    message.attach(MIMEText(body_text, "plain"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS) as server:
            _smtp_login(server)
            server.sendmail(GMAIL_FROM_ADDRESS, to_email, message.as_string())
    except (smtplib.SMTPException, OSError) as e:
        raise HTTPException(
            status_code=500,
            detail="Couldn't send the verification email. Please try again shortly.",
        ) from e


def send_password_reset_code(to_email: str, code: str) -> None:
    """Runs as a background task, after the HTTP response has already gone
    out (see the forgot-password endpoints) - so it can't raise to a caller;
    a failure is logged (never including the recipient's code or any
    credential) and the user simply requests another code. Sending after the
    response also means a real account and an unknown one take the same
    time to answer, so response timing can't be used to find out which
    emails are registered."""
    try:
        _send_reset_email(to_email, code)
    except HTTPException:
        logger.error("Password-reset email could not be sent")
    except Exception:  # noqa: BLE001 - a background task must never crash the worker
        logger.exception("Unexpected error sending password-reset email")


def _send_reset_email(to_email: str, code: str) -> None:
    send_email(
        to_email,
        subject="Your Zybrannox verification code",
        body_text=(
            f"Your password reset verification code is: {code}\n\n"
            "This code expires in 15 minutes. If you didn't request a "
            "password reset, you can safely ignore this email."
        ),
    )
