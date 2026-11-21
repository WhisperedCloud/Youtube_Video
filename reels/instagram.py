"""Publish a Reel with the official Instagram API (Instagram Login, free, no Facebook Page needed).

Flow: create a REELS container with resumable upload -> send the file bytes -> wait until Instagram
finishes processing -> publish. The long-lived token (60 days) is refreshed on every run.
"""
import os
import time

import requests

GRAPH = "https://graph.instagram.com"
VERSION = "v23.0"


def _check(r):
    if r.status_code >= 400:
        raise RuntimeError(f"Instagram API {r.status_code}: {r.text[:500]}")
    return r.json()


def account(token: str) -> dict:
    return _check(requests.get(f"{GRAPH}/{VERSION}/me", params={"fields": "user_id,username", "access_token": token}, timeout=30))


def refresh_token(token: str):
    """Return a fresh 60-day token, or None if Instagram refuses (e.g. token younger than 24 h)."""
    try:
        r = requests.get(f"{GRAPH}/refresh_access_token",
                         params={"grant_type": "ig_refresh_token", "access_token": token}, timeout=30)
        if r.ok and r.json().get("access_token"):
            return r.json()["access_token"]
        print(f"   ℹ️ token refresh skipped: {r.text[:200]}")
    except Exception as e:
        print(f"   ℹ️ token refresh failed: {e}")
    return None


def publish_reel(token: str, video_path: str, caption: str, thumb_offset_ms: int = 3000) -> dict:
    me = account(token)
    uid = me["user_id"]
    print(f"   📲 posting to @{me.get('username')}")

    c = _check(requests.post(f"{GRAPH}/{VERSION}/{uid}/media", timeout=60, data={
        "media_type": "REELS", "upload_type": "resumable", "caption": caption[:2200],
        "share_to_feed": "true", "thumb_offset": str(thumb_offset_ms), "access_token": token}))
    container = c["id"]
    upload_uri = c.get("uri") or f"https://rupload.facebook.com/ig-api-upload/{VERSION}/{container}"

    size = os.path.getsize(video_path)
    with open(video_path, "rb") as f:
        _check(requests.post(upload_uri, data=f, timeout=600, headers={
            "Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size)}))

    for _ in range(60):  # up to ~10 minutes
        s = _check(requests.get(f"{GRAPH}/{VERSION}/{container}", timeout=30,
                                params={"fields": "status_code,status", "access_token": token}))
        code = s.get("status_code")
        if code == "FINISHED":
            break
        if code in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram could not process the video: {s}")
        time.sleep(10)
    else:
        raise RuntimeError("Instagram processing timed out")

    pub = _check(requests.post(f"{GRAPH}/{VERSION}/{uid}/media_publish", timeout=60,
                               data={"creation_id": container, "access_token": token}))
    link = ""
    try:
        link = _check(requests.get(f"{GRAPH}/{VERSION}/{pub['id']}", timeout=30,
                                   params={"fields": "permalink", "access_token": token})).get("permalink", "")
    except Exception:
        pass
    return {"id": pub["id"], "permalink": link}
