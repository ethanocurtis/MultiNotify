import os
import praw
import requests
import asyncio
import discord
from datetime import datetime

# --- Load environment variables ---
REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT = os.environ.get("REDDIT_USER_AGENT", "reddit-discord-bot")
SUBREDDIT = os.environ.get("SUBREDDIT", "selfhosted")
ALLOWED_FLAIRS = [f.strip() for f in os.environ.get("ALLOWED_FLAIR", "").split(",") if f.strip()]
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", 300))
POST_LIMIT = int(os.environ.get("POST_LIMIT", 10))
DEBUG_MODE = os.environ.get("DEBUG", "false").lower() == "true"
ENABLE_DM = os.environ.get("ENABLE_DM", "false").lower() == "true"
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
DISCORD_USER_IDS = [uid.strip() for uid in os.environ.get("DISCORD_USER_IDS", "").split(",") if uid.strip()]

posted_ids = set()
discord_ready = asyncio.Event()  # Used to delay Reddit loop until Discord connects

# --- Set up Reddit API ---
reddit = praw.Reddit(
    client_id=REDDIT_CLIENT_ID,
    client_secret=REDDIT_CLIENT_SECRET,
    user_agent=REDDIT_USER_AGENT
)

# --- Persistent Discord Client ---
class DMClient(discord.Client):
    async def on_ready(self):
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Discord DM client connected as {self.user}")
        discord_ready.set()  # Signal that the bot is ready for DMs

    async def send_dm(self, user_id, message):
        try:
            user = await self.fetch_user(int(user_id))
            await user.send(message)
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] DM sent to {user_id}")
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Failed to DM {user_id}: {e}")

discord_client = DMClient(intents=discord.Intents.default()) if ENABLE_DM and DISCORD_BOT_TOKEN else None

# --- Helper: Send Webhook + DMs ---
async def send_post_notification(post):
    post_url = f"https://www.reddit.com{post.permalink}"
    flair_text = post.link_flair_text or "None"

    # Prepare webhook data
    if "discord.com" in WEBHOOK_URL:
        data = {
            "embeds": [{
                "title": post.title,
                "url": post_url,
                "description": f"**Flair:** {flair_text}\n\n{post.selftext[:500]}...",
                "footer": {"text": f"Posted by u/{post.author}"},
            }]
        }
    else:
        text_msg = f"New post on r/{SUBREDDIT}:\n{post.title} ({post_url})\nFlair: {flair_text}\nPosted by u/{post.author}"
        data = {"text": text_msg}

    # Send webhook
    response = requests.post(WEBHOOK_URL, json=data)
    if response.status_code not in (200, 204):
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Webhook error: {response.status_code} {response.text}")
    else:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Sent to webhook: {post.title}")

    # Send DMs if enabled
    if ENABLE_DM and discord_client:
        message = f"New Reddit post in r/{SUBREDDIT}: {post.title}\n{post_url}\nFlair: {flair_text}\nPosted by u/{post.author}"
        for uid in DISCORD_USER_IDS:
            await discord_client.send_dm(uid, message)

# --- Main Reddit Check Loop ---
async def reddit_loop():
    # Wait for Discord to be ready if DMs are enabled
    if ENABLE_DM:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Waiting for Discord bot to connect before starting Reddit checks...")
        await discord_ready.wait()
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Discord bot ready, starting Reddit checks.")

    while True:
        try:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Checking r/{SUBREDDIT} for flairs: {', '.join(ALLOWED_FLAIRS) if ALLOWED_FLAIRS else 'ANY'}")
            posts = list(reddit.subreddit(SUBREDDIT).new(limit=POST_LIMIT))
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Retrieved {len(posts)} posts to check.")
            found_post = False

            for post in posts:
                if ALLOWED_FLAIRS and post.link_flair_text not in ALLOWED_FLAIRS:
                    continue
                if not DEBUG_MODE and post.id in posted_ids:
                    continue

                posted_ids.add(post.id)  # Mark as sent to avoid duplicates
                await send_post_notification(post)
                found_post = True

            if not found_post:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] No new posts this cycle.")

        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Reddit fetch error: {e}")

        if DEBUG_MODE:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Debug mode active — exiting after one cycle.")
            break

        await asyncio.sleep(CHECK_INTERVAL)

# --- Run everything together ---
async def main():
    tasks = []

    # Start Reddit fetch loop
    tasks.append(asyncio.create_task(reddit_loop()))

    # Start Discord bot if enabled
    if ENABLE_DM and DISCORD_BOT_TOKEN:
        tasks.append(asyncio.create_task(discord_client.start(DISCORD_BOT_TOKEN)))

    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
