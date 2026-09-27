"""Heuristic: is this image a screenshot of somebody else's tweet?

OCRs the image with Tesseract, then looks for (a) an @handle that isn't the
poster's own and (b) enough tweet-UI markers (timestamps, "Reposts", "Views",
etc.) to be confident it's a tweet and not just a meme with a handle on it.
"""
import io
import re

HANDLE_RE = re.compile(r"@([A-Za-z0-9_]{2,15})\b")
# Tesseract often reads "@" as one of these.
AT_LOOKALIKES = re.compile(r"[©®]\s?(?=[A-Za-z0-9_]{2,15}\b)")

MARKERS = [
    re.compile(r"\b\d{1,2}:\d{2}\s?[AP]M\b", re.I),                  # 9:41 PM
    re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.? \d{1,2},? \d{4}\b"),
    re.compile(r"\b(Reposts?|Retweets?|Quotes?|Quote Tweets?)\b", re.I),
    re.compile(r"\b\d[\d.,]*[KM]?\s+(Views|Likes|Bookmarks)\b", re.I),
    re.compile(r"\bReplying to\b", re.I),
    re.compile(r"\b(Show more|Translate post|Show this thread)\b", re.I),
    re.compile(r"\b(Twitter for (iPhone|Android)|Twitter Web App)\b", re.I),
    re.compile(r"·\s*\d+[smhd]\b"),                                    # · 3h
]

MIN_MARKERS = 2


def find_handles(text):
    text = AT_LOOKALIKES.sub("@", text)
    return {h.lower() for h in HANDLE_RE.findall(text)}


def count_markers(text):
    return sum(1 for m in MARKERS if m.search(text))


def analyze_text(text, own_handle):
    """Return (is_other_persons_tweet, other_handles, marker_count)."""
    others = find_handles(text) - {own_handle.lower().lstrip("@")}
    markers = count_markers(text)
    return bool(others) and markers >= MIN_MARKERS, others, markers


def ocr(image_bytes):
    # Imported lazily so the rest of the bot (and tests) work without Tesseract.
    import pytesseract
    from PIL import Image, ImageOps, ImageStat

    img = Image.open(io.BytesIO(image_bytes)).convert("L")
    if ImageStat.Stat(img).mean[0] < 110:  # dark-mode screenshot
        img = ImageOps.invert(img)
    if img.width < 1200:
        scale = 1200 / img.width
        img = img.resize((1200, int(img.height * scale)))
    return pytesseract.image_to_string(img)


def is_tweet_screenshot(image_bytes, own_handle):
    try:
        text = ocr(image_bytes)
    except Exception:  # corrupt image, Tesseract missing, etc.
        return False
    return analyze_text(text, own_handle)[0]
