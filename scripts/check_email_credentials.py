"""Verifies the configured Gmail credentials by logging in to the SMTP server
- without sending anything. Run it after rotating the app password:

    ./venv/bin/python -m scripts.check_email_credentials

Prints only OK / the failure reason; the password itself is never printed.
"""
import smtplib
import sys

from app.email_service import check_credentials


def main() -> int:
    try:
        check_credentials()
    except smtplib.SMTPAuthenticationError:
        print("FAILED: Gmail rejected the credentials (wrong or revoked app password).")
        return 1
    except (smtplib.SMTPException, OSError) as e:
        print(f"FAILED: couldn't reach the mail server ({type(e).__name__}).")
        return 1
    except RuntimeError as e:
        print(f"FAILED: {e}")
        return 1
    print("OK: Gmail login succeeded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
