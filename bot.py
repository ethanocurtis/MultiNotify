import os
import praw
import requests
import asyncio
import discord
from discord.ext import commands
from datetime import datetime

# --- Always use /app/.env (project folder in Docker) ---
ENV_FILE = os.path.join("/app", ".env")
# --- Force-load .env at startup (same behavior as !reloadenv) ---
if os.path.exists(ENV_FILE):
    with open(ENV_FILE, "r") as f:
        for line in f:
            if "=" in line:
                key, value = line.strip().split("=", 1)
                os.environ[key] = value
    print(f"[DEBUG] Loaded environment from {ENV_FILE} at startup")
else:
    print(f"[WARN] No .env found at {ENV_FILE} on startup")

# --- Load environment variables ---
REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT = os.environ.get("REDDIT_USER_AGENT", "reddit-discord-bot")
SUBREDDIT = os.environ.get("SUBREDDIT", "selfhosted")
ALLOWED_FLAIRS = [f.strip() for f in os.environ.get("ALLOWED_FLAIR", "").split(",") if f.strip()]
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", 300))
POST_LIMIT = int(os.environ.get("POST_LIMIT", 10))
DEBUG_MODE = os.environ.get("DEBUG", "false").lower() == "true"
ENABLE_DM = os.environ.get("ENABLE_DM", "false").lower() == "true"
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
DISCORD_USER_IDS = [uid.strip() for uid in os.environ.get("DISCORD_USER_IDS", "").split(",") if uid.strip()]
ADMIN_USER_IDS = [uid.strip() for uid in os.environ.get("ADMIN_USER_IDS", "").split(",") if uid.strip()]

posted_ids = set()
last_check_time = "Never"  # Track last Reddit check

# --- Reddit API ---
reddit = praw.Reddit(
    client_id=REDDIT_CLIENT_ID,
    client_secret=REDDIT_CLIENT_SECRET,
    user_agent=REDDIT_USER_AGENT
)

# --- Discord bot setup ---
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
bot.remove_command("help")  # Disable default help

# --- Embed Helper ---
def make_embed(title, description=None, fields=None, color=0x3498db):
    embed = discord.Embed(title=title, description=description or "", color=color)
    if fields:
        for name, value, inline in fields:
            embed.add_field(name=name, value=value, inline=inline)
    return embed

# --- Update .env helper ---
def update_env_var(key, value):
    env_file = ENV_FILE
    env_path = os.path.abspath(env_file)
    print(f"[DEBUG] Writing {key}={value} to {env_path}")

    if not os.path.exists(env_file):
        try:
            with open(env_file, "w") as f:
                f.write(f"{key}={value}\n")
            os.environ[key] = value
            print(f"[DEBUG] Created new .env with {key}={value}")
            return
        except Exception as e:
            print(f"[ERROR] Could not create .env: {e}")
            return

    try:
        with open(env_file, "r") as f:
            lines = f.readlines()
    except Exception as e:
        print(f"[ERROR] Failed to read .env: {e}")
        return

    found = False
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[i] = f"{key}={value}\n"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}\n")

    try:
        with open(env_file, "w") as f:
            f.writelines(lines)
        os.environ[key] = value
        print(f"[DEBUG] Updated {key}={value} in {env_path}")
    except Exception as e:
        print(f"[ERROR] Failed to write {key}={value} to {env_path}: {e}")

# --- Reload env from file ---
def reload_env():
    global SUBREDDIT, ALLOWED_FLAIRS, WEBHOOK_URL, CHECK_INTERVAL, POST_LIMIT, ENABLE_DM, DISCORD_USER_IDS, ADMIN_USER_IDS
    env_file = ENV_FILE
    env_path = os.path.abspath(env_file)
    if not os.path.exists(env_file):
        print(f"[ERROR] No .env file found at {env_path}")
        return False
    try:
        with open(env_file, "r") as f:
            for line in f:
                if "=" in line:
                    key, value = line.strip().split("=", 1)
                    os.environ[key] = value
    except Exception as e:
        print(f"[ERROR] Failed to reload .env: {e}")
        return False

    SUBREDDIT = os.environ.get("SUBREDDIT", SUBREDDIT)
    ALLOWED_FLAIRS[:] = [f.strip() for f in os.environ.get("ALLOWED_FLAIR", "").split(",") if f.strip()]
    WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", WEBHOOK_URL)
    CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", CHECK_INTERVAL))
    POST_LIMIT = int(os.environ.get("POST_LIMIT", POST_LIMIT))
    ENABLE_DM = os.environ.get("ENABLE_DM", "false").lower() == "true"
    DISCORD_USER_IDS[:] = [uid.strip() for uid in os.environ.get("DISCORD_USER_IDS", "").split(",") if uid.strip()]
    ADMIN_USER_IDS[:] = [uid.strip() for uid in os.environ.get("ADMIN_USER_IDS", "").split(",") if uid.strip()]
    print(f"[DEBUG] Reloaded .env from {env_path}")
    return True

# --- Notification handler ---
async def send_post_notification(post):
    post_url = f"https://www.reddit.com{post.permalink}"
    flair_text = post.link_flair_text or "None"
    if WEBHOOK_URL:
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
        requests.post(WEBHOOK_URL, json=data)
    if ENABLE_DM and DISCORD_USER_IDS:
        message = f"New Reddit post in r/{SUBREDDIT}: {post.title}\n{post_url}\nFlair: {flair_text}\nPosted by u/{post.author}"
        for uid in DISCORD_USER_IDS:
            try:
                user = await bot.fetch_user(int(uid))
                await user.send(message)
            except Exception as e:
                print(f"Failed to DM {uid}: {e}")

# --- Reddit polling loop ---
async def reddit_loop():
    global posted_ids, last_check_time
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            last_check_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"[{last_check_time}] Checking r/{SUBREDDIT} for flairs: {', '.join(ALLOWED_FLAIRS) if ALLOWED_FLAIRS else 'ANY'}")
            posts = list(reddit.subreddit(SUBREDDIT).new(limit=POST_LIMIT))
            for post in posts:
                if ALLOWED_FLAIRS and post.link_flair_text not in ALLOWED_FLAIRS:
                    continue
                if not DEBUG_MODE and post.id in posted_ids:
                    continue
                await send_post_notification(post)
                posted_ids.add(post.id)
        except Exception as e:
            print(f"Reddit loop error: {e}")
        if DEBUG_MODE:
            break
        await asyncio.sleep(CHECK_INTERVAL)

# --- Admin check ---
def is_admin():
    async def predicate(ctx):
        return str(ctx.author.id) in ADMIN_USER_IDS
    return commands.check(predicate)

# --- Commands ---
@bot.command()
@is_admin()
async def setsubreddit(ctx, name: str = None):
    global SUBREDDIT
    if not name:
        await ctx.send(embed=make_embed("Current Subreddit", f"**{SUBREDDIT}**\nUsage: `!setsubreddit <subreddit>`"))
        return
    SUBREDDIT = name
    update_env_var("SUBREDDIT", name)
    await ctx.send(embed=make_embed("Setting Updated", f"Subreddit set to **{name}** (saved to .env)"))

@bot.command()
@is_admin()
async def setinterval(ctx, seconds: int = None):
    global CHECK_INTERVAL
    if seconds is None:
        await ctx.send(embed=make_embed("Current Interval", f"**{CHECK_INTERVAL} seconds**\nUsage: `!setinterval <seconds>`"))
        return
    CHECK_INTERVAL = seconds
    update_env_var("CHECK_INTERVAL", str(seconds))
    await ctx.send(embed=make_embed("Setting Updated", f"Check interval set to **{seconds} seconds** (saved to .env)"))

@bot.command()
@is_admin()
async def setpostlimit(ctx, number: int = None):
    global POST_LIMIT
    if number is None:
        await ctx.send(embed=make_embed("Current Post Limit", f"**{POST_LIMIT} posts** per check\nUsage: `!setpostlimit <number>`"))
        return
    POST_LIMIT = number
    update_env_var("POST_LIMIT", str(number))
    await ctx.send(embed=make_embed("Setting Updated", f"Post limit set to **{number}** (saved to .env)"))

@bot.command()
@is_admin()
async def setwebhook(ctx, url: str = None):
    global WEBHOOK_URL
    if url is None:
        current = WEBHOOK_URL if WEBHOOK_URL else "None (DM-only mode)"
        await ctx.send(embed=make_embed("Current Webhook URL", f"`{current}`\nUsage: `!setwebhook <url>`"))
        return
    WEBHOOK_URL = url
    update_env_var("DISCORD_WEBHOOK_URL", url)
    await ctx.send(embed=make_embed("Setting Updated", f"Webhook URL set to:\n`{url}` (saved to .env)"))

@bot.command()
@is_admin()
async def setflairs(ctx, *, flairs: str = None):
    global ALLOWED_FLAIRS
    if flairs is None:
        ALLOWED_FLAIRS = []
        update_env_var("ALLOWED_FLAIR", "")
        await ctx.send(embed=make_embed("Flairs Cleared", "Now accepting **ALL posts** (saved to .env)"))
        return
    ALLOWED_FLAIRS = [f.strip() for f in flairs.split(",") if f.strip()]
    update_env_var("ALLOWED_FLAIR", ",".join(ALLOWED_FLAIRS))
    await ctx.send(embed=make_embed("Setting Updated", f"Allowed flairs: **{', '.join(ALLOWED_FLAIRS) if ALLOWED_FLAIRS else 'ALL'}** (saved to .env)"))

@bot.command()
@is_admin()
async def enabledms(ctx, value: str = None):
    global ENABLE_DM
    if value is None:
        status = "enabled" if ENABLE_DM else "disabled"
        await ctx.send(embed=make_embed("DM Notifications", f"Currently **{status}**\nUsage: `!enabledms true/false`"))
        return
    ENABLE_DM = value.lower() == "true"
    update_env_var("ENABLE_DM", "true" if ENABLE_DM else "false")
    status = "enabled" if ENABLE_DM else "disabled"
    await ctx.send(embed=make_embed("Setting Updated", f"DM notifications **{status}** (saved to .env)"))

@bot.command()
@is_admin()
async def adddmuser(ctx, user_id: str = None):
    global DISCORD_USER_IDS
    if not user_id:
        await ctx.send(embed=make_embed("DM Users", f"Current users: **{', '.join(DISCORD_USER_IDS) if DISCORD_USER_IDS else 'None'}**\nUsage: `!adddmuser <user_id>`"))
        return
    if user_id not in DISCORD_USER_IDS:
        DISCORD_USER_IDS.append(user_id)
        update_env_var("DISCORD_USER_IDS", ",".join(DISCORD_USER_IDS))
        await ctx.send(embed=make_embed("User Added", f"User `{user_id}` added to DM list (saved to .env)"))
    else:
        await ctx.send(embed=make_embed("No Change", f"User `{user_id}` is already in the DM list"))

@bot.command()
@is_admin()
async def removedmuser(ctx, user_id: str = None):
    global DISCORD_USER_IDS
    if not user_id:
        await ctx.send(embed=make_embed("DM Users", f"Current users: **{', '.join(DISCORD_USER_IDS) if DISCORD_USER_IDS else 'None'}**\nUsage: `!removedmuser <user_id>`"))
        return
    if user_id in DISCORD_USER_IDS:
        DISCORD_USER_IDS.remove(user_id)
        update_env_var("DISCORD_USER_IDS", ",".join(DISCORD_USER_IDS))
        await ctx.send(embed=make_embed("User Removed", f"User `{user_id}` removed from DM list (saved to .env)"))
    else:
        await ctx.send(embed=make_embed("No Change", f"User `{user_id}` was not in the DM list"))

@bot.command()
@is_admin()
async def status(ctx):
    current_flairs = ", ".join(ALLOWED_FLAIRS) if ALLOWED_FLAIRS else "ALL"
    dm_status = "enabled" if ENABLE_DM else "disabled"
    dm_users = ", ".join(DISCORD_USER_IDS) if DISCORD_USER_IDS else "None"
    fields = [
        ("Subreddit", SUBREDDIT, True),
        ("Check Interval", f"{CHECK_INTERVAL} seconds", True),
        ("Post Limit", f"{POST_LIMIT} posts", True),
        ("Webhook URL", WEBHOOK_URL if WEBHOOK_URL else "None (DM-only mode)", False),
        ("Allowed Flairs", current_flairs, True),
        ("DM Notifications", dm_status, True),
        ("DM Users", dm_users, True),
        ("Last Reddit Check", last_check_time, False)
    ]
    await ctx.send(embed=make_embed("Bot Status", fields=fields))

@bot.command()
@is_admin()
async def reloadenv(ctx):
    if reload_env():
        await ctx.send(embed=make_embed("Reload Complete", "Environment variables reloaded from .env"))
    else:
        await ctx.send(embed=make_embed("Reload Failed", "Could not reload environment variables. Check logs."))

@bot.command()
@is_admin()
async def whereenv(ctx):
    await ctx.send(embed=make_embed("Environment File", f"Using `.env` at:\n`{os.path.abspath(ENV_FILE)}`"))

@bot.command()
@is_admin()
async def help(ctx):
    fields = [
        ("!setsubreddit [name]", "Set or show the subreddit being monitored.", False),
        ("!setinterval [seconds]", "Set or show how often Reddit is checked.", False),
        ("!setpostlimit [number]", "Set or show how many posts to fetch per check.", False),
        ("!setwebhook [url]", "Set or view the webhook URL (Discord, Slack, etc.).", False),
        ("!setflairs [flair1, flair2,...]", "Filter posts by flairs, or clear filter for all posts.", False),
        ("!enabledms [true/false]", "Enable/disable DM notifications or show status.", False),
        ("!adddmuser [user_id]", "Add a user to the DM list, or show the list.", False),
        ("!removedmuser [user_id]", "Remove a user from the DM list, or show the list.", False),
        ("!status", "Show bot settings and last Reddit check time.", False),
        ("!reloadenv", "Reload `.env` without restarting.", False),
        ("!whereenv", "Show the path of the `.env` file.", False),
    ]
    await ctx.send(embed=make_embed("Bot Commands", "Here’s a list of available commands:", fields))

# --- On Ready ---
@bot.event
async def on_ready():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Logged in as {bot.user}")
    bot.loop.create_task(reddit_loop())

bot.run(DISCORD_BOT_TOKEN)
