import base64
import os.path
from email.message import EmailMessage

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Scope for full access to send emails
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def get_credentials():
    creds = None
    # token.json stores the user's access and refresh tokens
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    # If there are no (valid) credentials available, let the user log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Save credentials for future runs (creates token.json)
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    return creds


def send_email(recipient, subject, body_text):
    creds = get_credentials()
    try:
        service = build("gmail", "v1", credentials=creds)

        message = EmailMessage()
        message.set_content(body_text)
        message["To"] = recipient
        message["Subject"] = subject

        # Encode the message in base64url format
        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {"raw": encoded_message}

        # Send the email
        send_message = (
            service.users()
            .messages()
            .send(userId="me", body=create_message)
            .execute()
        )
        print(f'Message sent! Message ID: {send_message["id"]}')

    except HttpError as error:
        print(f"An error occurred: {error}")


if __name__ == "__main__":
    send_email(
        recipient="assdiyousef@gmail.com",
        subject="Automated Test Email",
        body_text="Hello! This email was sent automatically using the Gmail API.",
    )