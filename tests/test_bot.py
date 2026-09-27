import datetime as dt
import random

from replybot import bot, picker, screenshot

ROTATION = [
    {"type": "image", "path": "media/a.jpg"},
    {"type": "image", "path": "media/b.jpg"},
    {"type": "link", "url": "https://example.com/1", "text": "Read:"},
]
CONTENT = {"rotation": ROTATION, "screenshot_reply": {"type": "image", "path": "media/ss.jpg"}}

TWEET_SHOT = """
Some Person @someone_else
This is a very bad take and I stand by it.
9:41 PM · Sep 3, 2026 · 1.2M Views
3,401 Reposts 812 Quotes 22K Likes
"""


def test_pick_never_repeats_recent():
    rng = random.Random(0)
    recent = []
    last = None
    for _ in range(200):
        item = picker.pick(ROTATION, recent, rng)
        assert picker.item_key(item) != last
        picker.remember(recent, item)
        last = picker.item_key(item)


def test_pick_single_item():
    assert picker.pick(ROTATION[:1], ["media/a.jpg"]) is ROTATION[0]


def test_detects_other_persons_tweet():
    hit, others, markers = screenshot.analyze_text(TWEET_SHOT, "target")
    assert hit and others == {"someone_else"} and markers >= 2


def test_ignores_own_tweet_screenshot():
    assert not screenshot.analyze_text(TWEET_SHOT.replace("someone_else", "Target"), "target")[0]


def test_ignores_meme_with_handle_watermark():
    assert not screenshot.analyze_text("when the coffee kicks in\n@memepage", "target")[0]


def test_ocr_lookalike_at_sign():
    assert screenshot.find_handles("© someone_else") == {"someone_else"}


def test_choose_reply_screenshot_wins():
    tweet = {"id": "1", "text": "lol", "image_urls": ["u1"]}
    item, reason = bot.choose_reply(tweet, CONTENT, {}, lambda u: True)
    assert reason == "screenshot" and item is CONTENT["screenshot_reply"]


def test_choose_reply_rotation_for_normal_post():
    tweet = {"id": "1", "text": "hi", "image_urls": []}
    state = {}
    item, reason = bot.choose_reply(tweet, CONTENT, state, lambda u: True)
    assert reason == "rotation" and item in ROTATION and state["recent"]


def test_build_post():
    assert bot.build_post(ROTATION[2]) == ("Read: https://example.com/1", None)
    assert bot.build_post(ROTATION[0]) == ("", "media/a.jpg")


def test_daily_cap_resets():
    state = {"day": "2020-01-01", "count": 99}
    assert bot.under_daily_cap(state, 5, dt.date(2026, 9, 27))
    state["count"] = 5
    assert not bot.under_daily_cap(state, 5, dt.date(2026, 9, 27))


class FakeX:
    def __init__(self, tweets):
        self.tweets, self.replies = tweets, []

    def get_user_id(self, name): return 42
    def latest_tweet_id(self, uid): return "100"
    def new_tweets(self, uid, since, include_replies): return [t for t in self.tweets if int(t["id"]) > int(since)]
    def download(self, url): return b""
    def upload_image(self, path): return "m-" + path
    def reply(self, tid, text, media_ids): self.replies.append((tid, text, media_ids)); return "r"


def test_run_once_first_run_initializes_without_replying():
    x, state = FakeX([{"id": "101", "text": "", "image_urls": []}]), {}
    cfg = {"target": "t", "max_per_day": 10, "include_replies": False, "dry_run": False}
    bot.run_once(x, cfg, CONTENT, state)
    assert state["since_id"] == "100" and x.replies == []
    bot.run_once(x, cfg, CONTENT, state)
    assert len(x.replies) == 1 and state["since_id"] == "101"


def test_run_once_respects_cap_and_dry_run():
    tweets = [{"id": str(i), "text": "", "image_urls": []} for i in range(101, 106)]
    x = FakeX(tweets)
    state = {"since_id": "100", "user_id": 42}
    cfg = {"target": "t", "max_per_day": 2, "include_replies": False, "dry_run": False}
    bot.run_once(x, cfg, CONTENT, state)
    assert len(x.replies) == 2 and state["since_id"] == "105"

    x2, state2 = FakeX(tweets), {"since_id": "100", "user_id": 42}
    bot.run_once(x2, dict(cfg, dry_run=True, max_per_day=10), CONTENT, state2)
    assert x2.replies == [] and state2["count"] == 5
