# replybot

Watches one X account. Whenever it posts:

- **If the post has an image that looks like a screenshot of someone else's tweet**, the bot replies with your special `screenshot_reply` image.
- **Otherwise** it replies with a random item from `rotation`: either an image or an article link. It won't repeat anything it used recently.

Screenshot detection runs locally with Tesseract OCR. An image counts as a screenshot if it shows an @handle that isn't the target's own, plus at least two bits of tweet UI (a timestamp, "Reposts", "1.2M Views", "Replying to", and so on). That keeps memes with a watermark handle from triggering it.

## Setup

1. **Install Tesseract**: `brew install tesseract` or `apt install tesseract-ocr`.
2. `pip install -r requirements.txt`
3. **Create an X developer app** at developer.x.com and give it **Read and write** permission. Generate an access token *while logged in as the bot account*. Reading timelines needs a paid API plan.
4. `cp .env.example .env` and fill it in.
5. **Put your images in `media/`** and edit `content.json`:

```json
{
  "rotation": [
    {"type": "image", "path": "media/pic1.jpg", "text": "optional caption"},
    {"type": "link",  "url": "https://example.com/article", "text": "optional lead-in"}
  ],
  "screenshot_reply": {"type": "image", "path": "media/screenshot_reply.jpg"}
}
```

6. **Run it**: `python -m replybot`

`DRY_RUN=true` is the default. In dry-run mode the bot only logs what it *would* post. Set `DRY_RUN=false` when you're happy with it.

## Behavior notes

- **First run:** the bot records the target's latest post and only replies to posts after it, so it won't dump replies on their whole backlog.
- **What gets a reply:** retweets are skipped. Replies are skipped too unless `INCLUDE_REPLIES=true`.
- **Daily cap:** `MAX_REPLIES_PER_DAY` (default 10) limits replies per day.
- **State:** progress is saved to `state.json` (last seen post and recent picks). On hosts with ephemeral disks (Heroku dynos), put it on a persistent volume, or accept that a restart re-initializes from "now".
- **Media upload** uses X's v2 endpoint (`POST https://api.x.com/2/media/upload`), because the v1.1 upload that tweepy wraps has been retired.

## Staying on X's good side

X's automation rules require the bot account to carry the "Automated" label, which you set in the account settings. Unsolicited automated replies to an account that hasn't opted in can get the bot suspended, so keep the daily cap sane.

## Tests

`python -m pytest tests`
