import os
import praw
import requests
import time
from datetime import datetime

# Load environment variables
REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT = os.environ.get("REDDIT_USER_AGENT", "reddit-discord-bot")
SUBREDDIT = os.environ.get("SUBREDDIT", "selfhosted")
ALLOWED_FLAIRS = [f.strip() for f in os.environ.get("ALLOWED_FLAIR", "").split(",") if f.strip()]
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", 300))
POST_LIMIT = int(os.environ.get("POST_LIMIT", 10))
DEBUG_MODE = os.environ.get("DEBUG", "false").lower() == "true"

posted_ids = set()

reddit = praw.Reddit(
    client_id=REDDIT_CLIENT_ID,
    client_secret=REDDIT_CLIENT_SECRET,
    user_agent=REDDIT_USER_AGENT
)

def send_to_discord(post):
    data = {
        "embeds": [{
            "title": post.title,
            "url": f"https://www.reddit.com{post.permalink}",
            "description": f"**Flair:** {post.link_flair_text or 'None'}\n\n{post.selftext[:500]}...",
            "footer": {"text": f"Posted by u/{post.author}"},
        }]
    }
    response = requests.post(DISCORD_WEBHOOK_URL, json=data)
    if response.status_code != 204:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Failed to send to Discord: {response.status_code} {response.text}")

while True:
    try:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Checking r/{SUBREDDIT} for flairs: {', '.join(ALLOWED_FLAIRS) if ALLOWED_FLAIRS else 'ANY'}")
        found_post = False
        posts = list(reddit.subreddit(SUBREDDIT).new(limit=POST_LIMIT))
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Retrieved {len(posts)} posts to check.")
        for post in posts:
            # Only filter by flair if ALLOWED_FLAIRS is not empty
            if ALLOWED_FLAIRS and post.link_flair_text not in ALLOWED_FLAIRS:
                continue
            # Skip already posted unless in debug mode
            if not DEBUG_MODE and post.id in posted_ids:
                continue
            try:
                send_to_discord(post)
                posted_ids.add(post.id)
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Posted to Discord: {post.title}")
                found_post = True
            except Exception as send_error:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Error sending post: {send_error}")
        if not found_post:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] No new matching posts found this cycle.")
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Error fetching posts: {e}")

    # Debug mode runs only once
    if DEBUG_MODE:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Debug mode active — processed once and exiting.")
        break

    time.sleep(CHECK_INTERVAL)
