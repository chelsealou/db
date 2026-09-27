"""Main loop: poll the target's timeline and reply to each new post."""
import datetime as dt
import json
import logging
import os
import time

from . import picker, screenshot

log = logging.getLogger("replybot")


def load_dotenv(path=".env"):
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def choose_reply(tweet, content, state, is_screenshot):
    """Screenshot of someone else's tweet -> the special image; else random rotation."""
    for url in tweet["image_urls"]:
        if is_screenshot(url):
            return content["screenshot_reply"], "screenshot"
    item = picker.pick(content["rotation"], state.setdefault("recent", []))
    picker.remember(state["recent"], item)
    return item, "rotation"


def build_post(item):
    """Return (text, image_path_or_None) for a content item."""
    text = item.get("text", "").strip()
    if item["type"] == "link":
        return f"{text} {item['url']}".strip(), None
    if item["type"] == "image":
        return text, item["path"]
    raise ValueError(f"unknown content type: {item['type']!r}")


def under_daily_cap(state, cap, today=None):
    today = (today or dt.date.today()).isoformat()
    if state.get("day") != today:
        state["day"], state["count"] = today, 0
    return state["count"] < cap


def run_once(x, cfg, content, state):
    user_id = state.get("user_id") or x.get_user_id(cfg["target"])
    state["user_id"] = user_id

    if not state.get("since_id"):
        # First run: start from "now" instead of replying to their whole backlog.
        state["since_id"] = x.latest_tweet_id(user_id)
        log.info("Initialized at tweet %s; will reply to posts after this.", state["since_id"])
        return

    def is_screenshot(url):
        return screenshot.is_tweet_screenshot(x.download(url), cfg["target"])

    for tweet in x.new_tweets(user_id, state["since_id"], cfg["include_replies"]):
        state["since_id"] = tweet["id"]
        if not under_daily_cap(state, cfg["max_per_day"]):
            log.warning("Daily cap (%d) reached; skipping %s", cfg["max_per_day"], tweet["id"])
            continue

        try:
            item, reason = choose_reply(tweet, content, state, is_screenshot)
            text, image = build_post(item)
            if cfg["dry_run"]:
                log.info("[dry run] would reply to %s (%s): text=%r image=%s",
                         tweet["id"], reason, text, image)
            else:
                media_ids = [x.upload_image(image)] if image else None
                reply_id = x.reply(tweet["id"], text, media_ids)
                log.info("Replied to %s with %s (%s)", tweet["id"], reply_id, reason)
            state["count"] += 1
        except Exception as e:
            # Rate limits bubble up so the main loop can back off; anything else
            # (deleted tweet, blocked, etc.) is logged and that tweet is skipped.
            if type(e).__name__ == "TooManyRequests":
                raise
            log.exception("Failed to reply to %s; skipping", tweet["id"])


def config_from_env():
    return {
        "target": os.environ["TARGET_USERNAME"].lstrip("@"),
        "content_file": os.environ.get("CONTENT_FILE", "content.json"),
        "state_file": os.environ.get("STATE_FILE", "state.json"),
        "poll_seconds": int(os.environ.get("POLL_SECONDS", "120")),
        "max_per_day": int(os.environ.get("MAX_REPLIES_PER_DAY", "10")),
        "include_replies": os.environ.get("INCLUDE_REPLIES", "false").lower() == "true",
        "dry_run": os.environ.get("DRY_RUN", "true").lower() != "false",
    }


def validate_content(content):
    items = content.get("rotation", []) + [content.get("screenshot_reply", {})]
    missing = [i["path"] for i in items if i.get("type") == "image" and not os.path.exists(i["path"])]
    if not content.get("rotation"):
        raise SystemExit("content.json: 'rotation' is empty")
    if "screenshot_reply" not in content:
        raise SystemExit("content.json: 'screenshot_reply' is missing")
    if missing:
        raise SystemExit(f"content.json references missing images: {missing}")


def main():
    import tweepy
    from .x_client import XClient

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_dotenv()
    cfg = config_from_env()
    content = load_json(cfg["content_file"], {})
    validate_content(content)
    x = XClient(
        os.environ["X_API_KEY"], os.environ["X_API_SECRET"],
        os.environ["X_ACCESS_TOKEN"], os.environ["X_ACCESS_TOKEN_SECRET"],
        os.environ.get("X_BEARER_TOKEN"),
    )
    log.info("Watching @%s every %ss (dry_run=%s)", cfg["target"], cfg["poll_seconds"], cfg["dry_run"])

    while True:
        state = load_json(cfg["state_file"], {})
        try:
            run_once(x, cfg, content, state)
        except tweepy.TooManyRequests as e:
            reset = int(e.response.headers.get("x-rate-limit-reset", time.time() + 900))
            wait = max(reset - time.time(), 60)
            log.warning("Rate limited; sleeping %ds", wait)
            save_json(cfg["state_file"], state)
            time.sleep(wait)
            continue
        except Exception:
            log.exception("Poll failed; will retry")
        save_json(cfg["state_file"], state)
        time.sleep(cfg["poll_seconds"])
