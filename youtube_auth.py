"""Run locally once to authorize the YouTube channel. Do not commit generated JSON files."""
from google_auth_oauthlib.flow import InstalledAppFlow
from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT_FILE = "client_secret.json"
if not Path(CLIENT_FILE).exists():
    raise SystemExit("Place your downloaded Desktop OAuth client JSON here as client_secret.json")
flow = InstalledAppFlow.from_client_secrets_file(CLIENT_FILE, SCOPES)
credentials = flow.run_local_server(port=0, access_type="offline", prompt="consent")
Path("token.json").write_text(credentials.to_json(), encoding="utf-8")
print("Created token.json. Keep it secret; never commit it.")
