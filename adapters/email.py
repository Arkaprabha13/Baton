"""Email adapter for Baton using native Python SMTP (sending) and IMAP (drafts)."""

import os
import smtplib
import imaplib
import time
import traceback
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.message import EmailMessage
from typing import Any
from dotenv import load_dotenv

# Ensure .env is loaded
load_dotenv()


async def send_email(to: str, subject: str, body: str) -> dict[str, Any]:
    """Send an email using Gmail SMTP directly.
    
    Args:
        to: Recipient email address.
        subject: Email subject line.
        body: Plain text email body.
        
    Returns:
        A dictionary with the status and a mock message_id.
    """
    gmail_user = os.getenv("GMAIL_USER")
    gmail_password = os.getenv("GMAIL_APP_PASSWORD")

    if not gmail_user or not gmail_password:
        print("   ❌ [SMTP] Error: GMAIL_USER or GMAIL_APP_PASSWORD is missing in .env")
        raise ValueError("Missing SMTP credentials in .env file")

    try:
        print(f"   📡 [SMTP] Connecting to Gmail to send to {to}...")

        # Create the email message container
        msg = MIMEMultipart()
        msg['From'] = gmail_user
        msg['To'] = to
        msg['Subject'] = subject

        # Attach the body to the email
        msg.attach(MIMEText(body, 'plain'))

        # Connect to Gmail's SMTP server (SSL, port 465)
        with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=15) as server:
            server.login(gmail_user, gmail_password)
            server.send_message(msg)

        print(f"   ✅ [SMTP] Email SENT successfully to {to}!")
        return {"status": "success", "message_id": "smtp_sent_successfully"}

    except smtplib.SMTPAuthenticationError:
        print("   ❌ [SMTP] Authentication Error: Check your App Password in .env")
        raise
    except smtplib.SMTPException as e:
        print(f"   ❌ [SMTP] SMTP Error occurred: {e}")
        traceback.print_exc()
        raise
    except Exception as e:
        print(f"   ❌ [SMTP] Unexpected Error: {e}")
        traceback.print_exc()
        raise


async def save_draft(to: str, subject: str, body: str) -> dict[str, Any]:
    """Save an email directly to the Gmail Drafts folder using IMAP.
    
    Args:
        to: Recipient email address (can be empty if no email found).
        subject: Email subject line.
        body: Plain text email body.
        
    Returns:
        A dictionary with the status.
    """
    gmail_user = os.getenv("GMAIL_USER")
    gmail_password = os.getenv("GMAIL_APP_PASSWORD")

    if not gmail_user or not gmail_password:
        print("   ❌ [IMAP] Error: Credentials missing in .env")
        raise ValueError("Missing credentials in .env file")

    try:
        print(f"   📡 [IMAP] Saving draft to Gmail Drafts folder...")
        
        # Create the email message
        msg = EmailMessage()
        msg['From'] = gmail_user
        # If there's no email, put your own email in the 'To' field so Gmail doesn't error
        msg['To'] = to if to else gmail_user 
        msg['Subject'] = subject
        msg.set_content(body)

        # Connect to Gmail IMAP server
        with imaplib.IMAP4_SSL("imap.gmail.com") as mail:
            mail.login(gmail_user, gmail_password)
            
            # Append the message to the "[Gmail]/Drafts" folder
            # The '\\Draft' flag tells Gmail to mark it as a draft
            mail.append(
                "[Gmail]/Drafts", 
                '\\Draft', 
                imaplib.Time2Internaldate(time.time()), 
                msg.as_bytes()
            )
            
        print(f"   ✅ [IMAP] Draft successfully saved to Gmail!")
        return {"status": "success", "message": "Draft saved to Gmail"}

    except Exception as e:
        print(f"   ❌ [IMAP] Failed to save draft: {repr(e)}")
        traceback.print_exc()
        raise


async def search_emails(query: str, max_results: int = 20) -> list[dict[str, Any]]:
    """Mock search function.
    
    Since we are using SMTP for sending and IMAP for drafts, we do not have 
    a full IMAP inbox poller configured yet. This returns an empty list so 
    the pipeline doesn't crash if it tries to poll for replies.
    """
    print(f"   ⚠️ [SMTP] Search emails for '{query}' skipped (Inbox polling not implemented).")
    return []