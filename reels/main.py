"""Make one Reel for one account and post it.

  python reels/main.py quiz     # "Guess the Place" account
  python reels/main.py stoic    # Stoic quotes account

Env: PIXABAY_API_KEY, GEMINI_API_KEY, IG_TOKEN_QUIZ / IG_TOKEN_STOIC.
With DRY_RUN=1, or when the account's token is not set yet, the Reel is rendered, checked and saved to
reels_output/ instead of being posted.
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import mark_used  # noqa: E402
import instagram  # noqa: E402
import qc  # noqa: E402
import quiz  # noqa: E402
import stoic  # noqa: E402

FORMATS = {"quiz": quiz, "stoic": stoic}
OUT_DIR = os.environ.get("OUT_DIR", "reels_output")


def main(acct: str) -> int:
    fmt = FORMATS[acct]
    token = os.environ.get(f"IG_TOKEN_{acct.upper()}", "").strip()
    dry = os.environ.get("DRY_RUN") == "1" or not token
    os.makedirs(OUT_DIR, exist_ok=True)

    handle = os.environ.get(f"IG_HANDLE_{acct.upper()}", "").strip().lstrip("@")
    if token:
        try:
            handle = instagram.account(token).get("username") or handle
        except Exception as e:
            print(f"❌ Instagram token for '{acct}' is not working: {e}")
            if not dry:
                return 1
    print(f"🎬 Account: {acct}  handle: @{handle or '?'}  mode: {'DRY RUN (save only)' if dry else 'POST'}")

    for attempt in (1, 2):
        work = tempfile.mkdtemp(prefix=f"reel_{acct}_")
        try:
            r = fmt.build(handle, work, dry)
            expected = r.get("duration", getattr(fmt, "DURATION", 12.0))
            ok, report = qc.check(r["video"], expected)
            print(f"   🔍 QC: {'✅ PASS' if ok else '❌ FAIL'} — {report}")
            print(f"   📝 {r['summary']}")
            if not ok:
                continue
            name = f"{acct}_{sum(f.startswith(acct) and f.endswith('.mp4') for f in os.listdir(OUT_DIR)) + 1}"
            shutil.copy(r["video"], os.path.join(OUT_DIR, f"{name}.mp4"))
            with open(os.path.join(OUT_DIR, f"{name}.txt"), "w") as f:
                f.write(r["caption"] + "\n")
            if dry:
                print(f"   💾 saved {OUT_DIR}/{name}.mp4 (not posted)")
                mark_used(acct, *r["used"]) if os.environ.get("MARK_USED_IN_DRY_RUN") == "1" else None
                return 0
            res = instagram.publish_reel(token, r["video"], r["caption"])
            print(f"   ✅ Posted: {res.get('permalink') or res['id']}")
            mark_used(acct, *r["used"])
            new = instagram.refresh_token(token)
            if new and new != token:
                with open(os.path.join(OUT_DIR, f"new_token_{acct}.secret"), "w") as f:
                    f.write(new)
            return 0
        except Exception as e:
            print(f"   ❌ attempt {attempt} failed: {e}")
        finally:
            shutil.rmtree(work, ignore_errors=True)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "quiz"))
