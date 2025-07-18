import os
import praw
import requests
import time

# Load environment variables
REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT = os.environ.get("REDDIT_USER_AGENT", "reddit-discord-bot")
SUBREDDIT = os.environ.get("SUBREDDIT", "selfhosted")
ALLOWED_FLAIR = os.environ.get("ALLOWED_FLAIR", "Product Announcement")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", 300))
POST_LIMIT = int(os.environ.get("POST_LIMIT", 10))

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
        print(f"Failed to send to Discord: {response.status_code} {response.text}")

while True:
    try:
        for post in reddit.subreddit(SUBREDDIT).new(limit=POST_LIMIT):
            if post.link_flair_text != ALLOWED_FLAIR:
                continue
            if post.id in posted_ids:
                continue
            send_to_discord(post)
            posted_ids.add(post.id)
            print(f"Posted: {post.title}")
    except Exception as e:
        print(f"Error: {e}")

    time.sleep(CHECK_INTERVAL)
