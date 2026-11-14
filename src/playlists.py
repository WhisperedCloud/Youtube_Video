"""Themed playlists: created on first use, every new video is added to its theme's playlist.
Playlists show up in YouTube search and keep viewers watching (session time), which helps ranking."""

PLAYLISTS = {
    "rain": {
        "title": "Rain Sounds for Sleeping 🌧️ Rain on Window, Thunderstorms & Forest Rain",
        "description": "Rain sounds for sleeping, studying and relaxing: rain on window, thunderstorm sounds, "
                       "heavy rain and gentle forest rain. New rain ambience every day from Rainora.",
        "topics": ["rain window", "thunderstorm night", "autumn forest rain"],
    },
    "fire": {
        "title": "Fireplace Sounds 🔥 Crackling Fire & Campfire Ambience for Sleep",
        "description": "Cozy fireplace sounds and crackling campfire ambience for sleep, reading and relaxation. "
                       "No music, no talking — just warm fire sounds.",
        "topics": ["cozy fireplace", "campfire crackling"],
    },
    "ocean": {
        "title": "Ocean Waves Sounds for Sleeping 🌊 Calming Sea Ambience",
        "description": "Ocean waves sounds for deep sleep, meditation and stress relief. Calming sea and beach "
                       "wave ambience at night.",
        "topics": ["ocean waves night"],
    },
    "study": {
        "title": "Study Ambience 📚 Cafe, Library & Train Sounds for Focus",
        "description": "Study ambience for focus and productivity: cozy cafe sounds, quiet library ambience and "
                       "night train rides. Perfect background sound for studying and working.",
        "topics": ["lofi cafe night", "library ambience", "train window night"],
    },
    "winter": {
        "title": "Cozy Winter Ambience ❄️ Snow Falling & Winter Night Sounds",
        "description": "Snow falling ambience and cozy winter night sounds for sleep and relaxation.",
        "topics": ["snow falling window"],
    },
    "shorts": {
        "title": "Relaxing Ambience Shorts 🌙 Instant Calm in 30 Seconds",
        "description": "30-second ambience Shorts: rain, fire, ocean and cozy sounds for instant calm.",
        "topics": [],
    },
}


def _playlist_key(topic: str, is_short: bool) -> str:
    if is_short:
        return "shorts"
    for key, p in PLAYLISTS.items():
        if topic in p["topics"]:
            return key
    return "rain"


def ensure_playlists(youtube) -> dict:
    """Return {key: playlistId}, creating any missing playlists (matched by title)."""
    existing, token = {}, None
    while True:
        resp = youtube.playlists().list(part="snippet", mine=True, maxResults=50, pageToken=token).execute()
        for it in resp.get("items", []):
            existing[it["snippet"]["title"]] = it["id"]
        token = resp.get("nextPageToken")
        if not token:
            break
    ids = {}
    for key, p in PLAYLISTS.items():
        if p["title"] in existing:
            ids[key] = existing[p["title"]]
        else:
            body = {"snippet": {"title": p["title"], "description": p["description"], "defaultLanguage": "en"},
                    "status": {"privacyStatus": "public"}}
            ids[key] = youtube.playlists().insert(part="snippet,status", body=body).execute()["id"]
            print(f"   -> Created playlist: {p['title']}")
    return ids


def add_to_playlist(youtube, video_id: str, topic: str, is_short: bool) -> None:
    try:
        ids = ensure_playlists(youtube)
        pid = ids[_playlist_key(topic, is_short)]
        youtube.playlistItems().insert(part="snippet", body={
            "snippet": {"playlistId": pid, "resourceId": {"kind": "youtube#video", "videoId": video_id}}
        }).execute()
        print("   -> Added to playlist")
    except Exception as e:  # needs the 'youtube' scope; never block the upload on this
        print(f"   ⚠️ Playlist step skipped: {str(e)[:150]}")
