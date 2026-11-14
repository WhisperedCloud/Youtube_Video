"""
One-time helper: generates YT_REFRESH_TOKEN for the channel that the bot will upload to.

Usage:
  1. Put YT_CLIENT_ID and YT_CLIENT_SECRET in .env
  2. python get_refresh_token.py
  3. A browser opens -> sign in with the Google account that OWNS the YouTube channel
     (if it's a brand channel, pick the channel when asked).
  4. The refresh token is written into .env automatically.
"""
import os
import sys
import webbrowser
from dotenv import load_dotenv, set_key
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


def main():
    load_dotenv(ENV_FILE)
    client_id = os.environ.get("YT_CLIENT_ID")
    client_secret = os.environ.get("YT_CLIENT_SECRET")
    if not client_id or not client_secret or client_id.startswith("<"):
        raise SystemExit("❌ Set YT_CLIENT_ID and YT_CLIENT_SECRET in .env first.")

    flow = InstalledAppFlow.from_client_config(
        {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"],
            }
        },
        SCOPES,
    )
    # Always open the sign-in page in a Chrome Incognito window (no stray logged-in accounts).
    if sys.platform == "darwin":
        incognito_cmd = ["open", "-na", "Google Chrome", "--args", "--incognito", "%s"]
    else:
        incognito_cmd = ["google-chrome", "--incognito", "%s"]
    webbrowser.register("chrome-incognito", None, webbrowser.GenericBrowser(incognito_cmd))

    # prompt=consent forces Google to return a refresh token every time
    creds = flow.run_local_server(
        port=8080,  # fixed so it matches the redirect URI http://localhost:8080/ on the OAuth client
        access_type="offline",
        prompt="consent select_account",
        login_hint=os.environ.get("YT_LOGIN_HINT", ""),
        browser="chrome-incognito",
        authorization_prompt_message="If the browser didn't open, paste this URL into an Incognito window:\n{url}\n",
    )

    if not creds.refresh_token:
        raise SystemExit("❌ No refresh token returned. Remove the app's access at myaccount.google.com/permissions and retry.")

    set_key(ENV_FILE, "YT_REFRESH_TOKEN", creds.refresh_token)
    print("✅ YT_REFRESH_TOKEN saved to .env")
    print("   Also add it as a GitHub secret named YT_REFRESH_TOKEN.")


if __name__ == "__main__":
    main()
