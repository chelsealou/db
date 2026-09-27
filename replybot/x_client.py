"""Thin wrapper around the X API (v2) for the handful of calls we need."""
import mimetypes

import requests
import tweepy
from requests_oauthlib import OAuth1

MEDIA_UPLOAD_URL = "https://api.x.com/2/media/upload"


class XClient:
    def __init__(self, api_key, api_secret, access_token, access_secret, bearer_token=None):
        self.client = tweepy.Client(
            bearer_token=bearer_token,
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_secret,
        )
        self.auth = OAuth1(api_key, api_secret, access_token, access_secret)

    def get_user_id(self, username):
        resp = self.client.get_user(username=username.lstrip("@"), user_auth=True)
        if resp.data is None:
            raise RuntimeError(f"X user @{username} not found")
        return resp.data.id

    def new_tweets(self, user_id, since_id=None, include_replies=False):
        """Return tweets newer than since_id, oldest first, as plain dicts."""
        exclude = ["retweets"] if include_replies else ["retweets", "replies"]
        resp = self.client.get_users_tweets(
            user_id,
            since_id=since_id,
            max_results=20,
            exclude=exclude,
            expansions=["attachments.media_keys"],
            media_fields=["type", "url"],
            tweet_fields=["attachments", "created_at"],
            user_auth=True,
        )
        media = {m.media_key: m for m in (resp.includes or {}).get("media", [])}
        tweets = []
        for t in resp.data or []:
            keys = (t.attachments or {}).get("media_keys", [])
            images = [media[k].url for k in keys
                      if k in media and media[k].type == "photo" and media[k].url]
            tweets.append({"id": str(t.id), "text": t.text, "image_urls": images})
        return sorted(tweets, key=lambda t: int(t["id"]))

    def latest_tweet_id(self, user_id):
        resp = self.client.get_users_tweets(user_id, max_results=5, user_auth=True)
        return str(resp.data[0].id) if resp.data else None

    def download(self, url):
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        return r.content

    def upload_image(self, path):
        mime = mimetypes.guess_type(path)[0] or "image/jpeg"
        with open(path, "rb") as f:
            r = requests.post(
                MEDIA_UPLOAD_URL,
                auth=self.auth,
                files={"media": (path.rsplit("/", 1)[-1], f, mime)},
                data={"media_category": "tweet_image"},
                timeout=60,
            )
        r.raise_for_status()
        return r.json()["data"]["id"]

    def reply(self, tweet_id, text="", media_ids=None):
        resp = self.client.create_tweet(
            text=text or None,
            in_reply_to_tweet_id=tweet_id,
            media_ids=media_ids,
        )
        return resp.data["id"]
