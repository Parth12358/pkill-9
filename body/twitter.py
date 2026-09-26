"""tweet(): link-free, <=280 chars, only ever called after approval. (PRD A: Twitter)

Live posting needs PKILL9_TWEETS_LIVE=1 plus X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN,
X_ACCESS_SECRET in env. Otherwise it's a dry run that just prints.
"""

import os
import re

URL = re.compile(r"(https?://\S+|www\.\S+|\b\S+\.(com|net|org|io|ai|dev|co|ly|me|gg|xyz)(/\S*)?\b)", re.I)
MENTION = re.compile(r"(?<!\w)@\w+")  # no pinging strangers


def sanitize(text: str) -> str:
    """Links cost ~13x per post, mentions are cold outreach: strip both, cap at 280."""
    text = URL.sub("", text or "")
    text = MENTION.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:280]


def _client():
    import tweepy  # only needed when live
    return tweepy.Client(
        consumer_key=os.environ["X_API_KEY"],
        consumer_secret=os.environ["X_API_SECRET"],
        access_token=os.environ["X_ACCESS_TOKEN"],
        access_token_secret=os.environ["X_ACCESS_SECRET"],
    )


def tweet(text: str) -> bool:
    text = sanitize(text)
    if not text:
        return False
    if os.environ.get("PKILL9_TWEETS_LIVE") != "1":
        print(f"[tweet dry-run] {text}", flush=True)
        return True
    try:
        _client().create_tweet(text=text)
        print(f"[tweeted] {text}", flush=True)
        return True
    except Exception as e:  # never let X take down the loop
        print(f"[tweet failed] {e}", flush=True)
        return False
