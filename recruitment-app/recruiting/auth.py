"""Shared Google OAuth for Drive + Calendar.

One consent screen, one cached token, used by both clients in this package.
This is the same idea as the GUC login in `guc_portal`/`guc_cms`: you supply
credentials once, and everything after that is plain API calls.
"""

from __future__ import annotations

from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# drive.readonly: this app only ever reads resumes/JDs, never writes to Drive.
# calendar: read (freebusy) and write (booking an interview) both need this.
SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/calendar",
]

_DEFAULT_CREDENTIALS = Path("credentials.json")
_DEFAULT_TOKEN = Path("token.json")


def get_credentials(
    credentials_path: str | Path = _DEFAULT_CREDENTIALS,
    token_path: str | Path = _DEFAULT_TOKEN,
) -> Credentials:
    """A logged-in Google credential; browser consent happens once.

    Needs `credentials.json` next to it: an OAuth "Desktop app" client
    downloaded from Google Cloud Console (see README for the exact steps).
    After the first run, `token.json` caches the login so you are not asked
    again. Never commit either file.
    """
    credentials_path, token_path = Path(credentials_path), Path(token_path)
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not credentials_path.exists():
                raise FileNotFoundError(
                    f"Missing {credentials_path}. Download an OAuth 'Desktop app' "
                    "client from Google Cloud Console and save it there (see README)."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json())
    return creds
