import os
import time
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

def upload_to_youtube(video_file: str, title: str, description: str, tags: list, is_short: bool = False, max_retries: int = 3, privacy: str = "public", publish_at: str = None, thumbnail: str = None) -> bool:
    client_id = os.environ.get("YT_CLIENT_ID")
    client_secret = os.environ.get("YT_CLIENT_SECRET")
    refresh_token = os.environ.get("YT_REFRESH_TOKEN")

    if not client_id or not client_secret or not refresh_token:
        print("❌ Error: YouTube OAuth credentials missing.")
        return False

    credentials = Credentials(
        token=None,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        token_uri="https://oauth2.googleapis.com/token"
    )

    # Build the YouTube client safely using only credentials
    youtube = build("youtube", "v3", credentials=credentials)

    body = {
        "snippet": {
            "title": title[:100],
            "description": description,
            "tags": tags,
            "categoryId": "10",  # Music: where sleep / study / ambience channels rank
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en",
        },
        "status": {
            "privacyStatus": privacy,  # "public", "private" or "unlisted"
            "selfDeclaredMadeForKids": False
        }
    }

    # Scheduled publishing: upload as private, YouTube flips it public at publishAt (RFC 3339, UTC).
    if publish_at:
        body["status"]["privacyStatus"] = "private"
        body["status"]["publishAt"] = publish_at
        print(f"   -> Scheduled to go public at {publish_at}")

    # Use 5MB chunk size for upload stability
    media = MediaFileUpload(video_file, chunksize=5 * 1024 * 1024, resumable=True)

    print(f"   -> Uploading {'Short' if is_short else 'Long-Form'} video to YouTube...")
    
    for attempt in range(1, max_retries + 1):
        try:
            request = youtube.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media
            )

            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    print(f"   -> Progress: {int(status.progress() * 100)}%")

            video_id = response.get("id")
            print(f"✅ Successfully uploaded! Video ID: {video_id}")
            if thumbnail and os.path.exists(thumbnail):
                try:
                    youtube.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(thumbnail, mimetype="image/jpeg")).execute()
                    print("   -> Custom thumbnail set")
                except Exception as te:
                    print(f"   ⚠️ Thumbnail not set (channel must be phone-verified at youtube.com/verify): {str(te)[:150]}")
            return True

        except (HttpError, Exception) as e:
            print(f"⚠️ Upload attempt {attempt} failed due to error: {e}")
            if attempt < max_retries:
                wait_time = attempt * 5
                print(f"   -> Retrying upload in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                print("❌ All upload retry attempts failed.")
                return False

    return False