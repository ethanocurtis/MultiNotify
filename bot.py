
import os
import praw
import requests
import asyncio
import discord
import re
from discord import app_commands
from datetime import datetime

ENV_FILE = os.path.join("/app", ".env")
if os.path.exists(ENV_FILE):
    with open(ENV_FILE, "r") as f:
        for line in f:
            if "=" in line:
                key, value = line.strip().split("=", 1)
                os.environ[key] = value
    print(f"[DEBUG] Loaded environment from {ENV_FILE} at startup")
else:
    print(f"[WARN] No .env found at {ENV_FILE} on startup")

REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT = os.environ.get("REDDIT_USER_AGENT", "reddit-discord-bot")
SUBREDDIT = os.environ.get("SUBREDDIT", "selfhosted")
ALLOWED_FLAIRS = [f.strip() for f in os.environ.get("ALLOWED_FLAIR", "").split(",") if f.strip()]
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", 300))
POST_LIMIT = int(os.environ.get("POST_LIMIT", 10))
ENABLE_DM = os.environ.get("ENABLE_DM", "false").lower() == "true"
DISCORD_USER_IDS = [u.strip() for u in os.environ.get("DISCORD_USER_IDS", "").split(",") if u.strip()]
ADMIN_USER_IDS = [u.strip() for u in os.environ.get("ADMIN_USER_IDS", "").split(",") if u.strip()]
KEYWORDS = [k.strip().lower() for k in os.environ.get("KEYWORDS", "").split(",") if k.strip()]
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")

reddit = praw.Reddit(
    client_id=REDDIT_CLIENT_ID,
    client_secret=REDDIT_CLIENT_SECRET,
    user_agent=REDDIT_USER_AGENT
)

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)
last_post_ids = set()

def update_env_var(key, value):
    lines = []
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r") as f:
            lines = f.readlines()
    updated = False
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}\n"
            updated = True
            break
    if not updated:
        lines.append(f"{key}={value}\n")
    with open(ENV_FILE, "w") as f:
        f.writelines(lines)

def make_embed(title, description, color=discord.Color.blue()):
    embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.utcnow())
    embed.set_footer(text="MultiNotify Bot", icon_url="https://www.redditstatic.com/desktop2x/img/favicon/android-icon-192x192.png")
    return embed

async def send_webhook_notification(post):
    if not WEBHOOK_URL:
        return
    flair = post.link_flair_text if post.link_flair_text else "No Flair"
    post_url = f"https://reddit.com{post.permalink}"
    if "discord.com" in WEBHOOK_URL:
        embed = discord.Embed(
            title=post.title,
            url=post_url,
            description=f"Subreddit: r/{SUBREDDIT}\nFlair: **{flair}**\nAuthor: u/{post.author}",
            color=discord.Color.orange(),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="MultiNotify Bot", icon_url="https://www.redditstatic.com/desktop2x/img/favicon/android-icon-192x192.png")
        try:
            requests.post(WEBHOOK_URL, json={"embeds": [embed.to_dict()]}, timeout=10)
        except Exception as e:
            print(f"[ERROR] Failed to send Discord webhook embed: {e}")
    else:
        msg = f"New post in r/{SUBREDDIT} ({flair}) by u/{post.author}: {post.title} ({post_url})"
        try:
            requests.post(WEBHOOK_URL, json={"text": msg}, timeout=10)
        except Exception as e:
            print(f"[ERROR] Failed to send non-Discord webhook: {e}")

def matches_keywords(post):
    if not KEYWORDS:
        return True
    content = f"{post.title} {post.selftext}".lower()
    return any(re.search(rf"\b{re.escape(kw)}\b", content) for kw in KEYWORDS)

async def fetch_and_notify():
    global last_post_ids
    await client.wait_until_ready()
    while not client.is_closed():
        try:
            subreddit = reddit.subreddit(SUBREDDIT)
            new_posts = []
            for submission in subreddit.new(limit=POST_LIMIT):
                print(f"[DEBUG] Checking post: {submission.title}")
                if not matches_keywords(submission):
                    print(f"[DEBUG] Post skipped due to keyword mismatch.")
                    continue
                elif ALLOWED_FLAIRS and submission.link_flair_text not in ALLOWED_FLAIRS:
                    print(f"[DEBUG] Post skipped due to flair mismatch: {submission.link_flair_text}")
                    continue
                elif submission.id in last_post_ids:
                    print(f"[DEBUG] Post already seen.")
                    continue
                print(f"[DEBUG] Post matched and will notify.")

                if ALLOWED_FLAIRS and submission.link_flair_text not in ALLOWED_FLAIRS:
                    continue
                if not matches_keywords(submission):
                    continue
                if submission.id not in last_post_ids:
                    last_post_ids.add(submission.id)
                    new_posts.append(submission)

            for post in reversed(new_posts):
                await send_webhook_notification(post)
                if ENABLE_DM and DISCORD_USER_IDS:
                    flair = post.link_flair_text if post.link_flair_text else "No Flair"
                    post_url = f"https://reddit.com{post.permalink}"
                    for uid in DISCORD_USER_IDS:
                        user = await client.fetch_user(int(uid))
                        try:
                            await user.send(f"New post in r/{SUBREDDIT} (Flair: {flair}) by u/{post.author}: {post.title} ({post_url})")
                        except Exception as e:
                            print(f"[ERROR] Failed to DM {uid}: {e}")
        except Exception as e:
            print(f"[ERROR] Reddit fetch failed: {e}")
        await asyncio.sleep(CHECK_INTERVAL)

def is_admin(interaction: discord.Interaction):
    return str(interaction.user.id) in ADMIN_USER_IDS

# Slash commands
@tree.command(name="setsubreddit", description="Set subreddit to monitor")
async def setsubreddit(interaction: discord.Interaction, name: str):
    if not is_admin(interaction):
        return await interaction.response.send_message(embed=make_embed("Unauthorized", "You are not authorized."), ephemeral=True)
    global SUBREDDIT
    SUBREDDIT = name
    update_env_var("SUBREDDIT", name)
    await interaction.response.send_message(embed=make_embed("Subreddit Updated", f"Now monitoring r/{name}", discord.Color.green()), ephemeral=True)

@tree.command(name="setinterval", description="Set interval (in seconds)")
async def setinterval(interaction: discord.Interaction, seconds: int):
    if not is_admin(interaction):
        return await interaction.response.send_message(embed=make_embed("Unauthorized", "You are not authorized."), ephemeral=True)
    global CHECK_INTERVAL
    CHECK_INTERVAL = seconds
    update_env_var("CHECK_INTERVAL", str(seconds))
    await interaction.response.send_message(embed=make_embed("Interval Updated", f"Now checking every {seconds} seconds", discord.Color.green()), ephemeral=True)

@tree.command(name="setpostlimit", description="Set number of posts to check")
async def setpostlimit(interaction: discord.Interaction, number: int):
    if not is_admin(interaction):
        return await interaction.response.send_message(embed=make_embed("Unauthorized", "You are not authorized."), ephemeral=True)
    global POST_LIMIT
    POST_LIMIT = number
    update_env_var("POST_LIMIT", str(number))
    await interaction.response.send_message(embed=make_embed("Post Limit Updated", f"Now checking {number} posts", discord.Color.green()), ephemeral=True)

@tree.command(name="setwebhook", description="Set webhook URL or clear")
async def setwebhook(interaction: discord.Interaction, url: str = ""):
    if not is_admin(interaction):
        return await interaction.response.send_message(embed=make_embed("Unauthorized", "You are not authorized."), ephemeral=True)
    global WEBHOOK_URL
    WEBHOOK_URL = url.strip()
    update_env_var("DISCORD_WEBHOOK_URL", WEBHOOK_URL)
    await interaction.response.send_message(embed=make_embed("Webhook Updated", f"Webhook URL set to: `{WEBHOOK_URL}`", discord.Color.green()), ephemeral=True)

@tree.command(name="setflairs", description="Set allowed flairs (comma separated)")
async def setflairs(interaction: discord.Interaction, flairs: str = ""):
    if not is_admin(interaction):
        return await interaction.response.send_message(embed=make_embed("Unauthorized", "You are not authorized."), ephemeral=True)
    global ALLOWED_FLAIRS
    ALLOWED_FLAIRS = [f.strip() for f in flairs.split(",") if f.strip()]
    update_env_var("ALLOWED_FLAIR", ",".join(ALLOWED_FLAIRS))
    await interaction.response.send_message(embed=make_embed("Flairs Updated", f"Now filtering flairs: {', '.join(ALLOWED_FLAIRS)}", discord.Color.green()), ephemeral=True)

@tree.command(name="enabledms", description="Enable or disable DMs")
async def enabledms(interaction: discord.Interaction, value: bool):
    if not is_admin(interaction):
        return await interaction.response.send_message(embed=make_embed("Unauthorized", "You are not authorized."), ephemeral=True)
    global ENABLE_DM
    ENABLE_DM = value
    update_env_var("ENABLE_DM", str(value).lower())
    await interaction.response.send_message(embed=make_embed("DM Setting Updated", f"DMs {'enabled' if value else 'disabled'}", discord.Color.green()), ephemeral=True)

@tree.command(name="adddmuser", description="Add user to DM list")
async def adddmuser(interaction: discord.Interaction, user_id: str):
    if not is_admin(interaction):
        return await interaction.response.send_message(embed=make_embed("Unauthorized", "You are not authorized."), ephemeral=True)
    if user_id not in DISCORD_USER_IDS:
        DISCORD_USER_IDS.append(user_id)
        update_env_var("DISCORD_USER_IDS", ",".join(DISCORD_USER_IDS))
    await interaction.response.send_message(embed=make_embed("DM User Added", f"Added user ID: {user_id}", discord.Color.green()), ephemeral=True)

@tree.command(name="removedmuser", description="Remove user from DM list")
async def removedmuser(interaction: discord.Interaction, user_id: str):
    if not is_admin(interaction):
        return await interaction.response.send_message(embed=make_embed("Unauthorized", "You are not authorized."), ephemeral=True)
    if user_id in DISCORD_USER_IDS:
        DISCORD_USER_IDS.remove(user_id)
        update_env_var("DISCORD_USER_IDS", ",".join(DISCORD_USER_IDS))
    await interaction.response.send_message(embed=make_embed("DM User Removed", f"Removed user ID: {user_id}", discord.Color.green()), ephemeral=True)

@tree.command(name="reloadenv", description="Reload environment from .env")
async def reloadenv(interaction: discord.Interaction):
    if not is_admin(interaction):
        return await interaction.response.send_message(embed=make_embed("Unauthorized", "You are not authorized."), ephemeral=True)
    os.execv(__file__, ['python'] + sys.argv)

@tree.command(name="whereenv", description="Show current .env path")
async def whereenv(interaction: discord.Interaction):
    await interaction.response.send_message(embed=make_embed("Environment File", f"`{ENV_FILE}`"), ephemeral=True)

@tree.command(name="setkeywords", description="Set or clear keywords to filter (comma separated, blank for all)")
async def setkeywords(interaction: discord.Interaction, words: str = ""):
    if not is_admin(interaction):
        return await interaction.response.send_message(embed=make_embed("Unauthorized", "You are not authorized to use this command.", discord.Color.red()), ephemeral=True)
    global KEYWORDS
    KEYWORDS = [w.strip().lower() for w in words.split(",") if w.strip()] if words else []
    update_env_var("KEYWORDS", ",".join(KEYWORDS))
    if KEYWORDS:
        await interaction.response.send_message(embed=make_embed("Keywords Updated", f"Filtering posts with keywords: {', '.join(KEYWORDS)}", discord.Color.green()), ephemeral=True)
    else:
        await interaction.response.send_message(embed=make_embed("Keywords Cleared", "No keywords set. All posts will be considered.", discord.Color.green()), ephemeral=True)

@tree.command(name="status", description="Show current monitoring status")
async def status(interaction: discord.Interaction):
    flair_list = ", ".join(ALLOWED_FLAIRS) if ALLOWED_FLAIRS else "ALL"
    dm_status = "enabled" if ENABLE_DM else "disabled"
    webhook_text = WEBHOOK_URL if WEBHOOK_URL else "None"
    dm_users = ", ".join(DISCORD_USER_IDS) if DISCORD_USER_IDS else "None"
    keyword_text = ", ".join(KEYWORDS) if KEYWORDS else "ALL"
    msg = (
        f"Monitoring r/{SUBREDDIT} every **{CHECK_INTERVAL}s**.\n"
        f"Post limit: **{POST_LIMIT}**.\n"
        f"Flairs: **{flair_list}**.\n"
        f"Keywords: **{keyword_text}**.\n"
        f"DMs: **{dm_status}** (Users: {dm_users}).\n"
        f"Webhook: `{webhook_text}`"
    )
    await interaction.response.send_message(embed=make_embed("Bot Status", msg), ephemeral=True)

@tree.command(name="help", description="Show help for commands")
async def help(interaction: discord.Interaction):
    commands_text = "\n".join([
        "/setsubreddit <name>",
        "/setinterval <seconds>",
        "/setpostlimit <number>",
        "/setwebhook <url or blank>",
        "/setflairs [comma separated]",
        "/setkeywords [comma separated]",
        "/enabledms <true/false>",
        "/adddmuser <user_id>",
        "/removedmuser <user_id>",
        "/status",
        "/reloadenv",
        "/whereenv"
    ])
    await interaction.response.send_message(embed=make_embed("Help", f"**Available Commands:**\n{commands_text}"), ephemeral=True)

@client.event
async def on_ready():
    await tree.sync()
    print(f"Logged in as {client.user}")
    client.loop.create_task(fetch_and_notify())

client.run(DISCORD_TOKEN)