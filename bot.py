
import os
import sys
import praw
import requests
import asyncio
import discord
import re
import feedparser
from discord import app_commands
from datetime import datetime
from urllib.parse import urlparse

# ---------- .env loader (container-friendly) ----------
ENV_FILE = os.path.join("/app", ".env")
if os.path.exists(ENV_FILE):
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if "=" in line:
                key, value = line.strip().split("=", 1)
                os.environ[key] = value
    print(f"[DEBUG] Loaded environment from {ENV_FILE} at startup")
else:
    print(f"[WARN] No .env found at {ENV_FILE} on startup")

# ---------- Environment ----------
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

# NEW: Separate keywords for Reddit vs RSS (with backward-compat for legacy KEYWORDS)
LEGACY_KEYWORDS = [k.strip().lower() for k in os.environ.get("KEYWORDS", "").split(",") if k.strip()]
REDDIT_KEYWORDS = [k.strip().lower() for k in os.environ.get("REDDIT_KEYWORDS", "").split(",") if k.strip()] or LEGACY_KEYWORDS
RSS_KEYWORDS = [k.strip().lower() for k in os.environ.get("RSS_KEYWORDS", "").split(",") if k.strip()]

# NEW: RSS feeds and channel IDs
RSS_FEEDS = [u.strip() for u in os.environ.get("RSS_FEEDS", "").split(",") if u.strip()]
RSS_LIMIT = int(os.environ.get("RSS_LIMIT", 10))
DISCORD_CHANNEL_IDS = [c.strip() for c in os.environ.get("DISCORD_CHANNEL_IDS", "").split(",") if c.strip()]

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")

# ---------- Clients ----------
reddit = praw.Reddit(
    client_id=REDDIT_CLIENT_ID,
    client_secret=REDDIT_CLIENT_SECRET,
    user_agent=REDDIT_USER_AGENT
)

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# ---------- State ----------
last_post_ids = set()
rss_last_ids = set()  # track seen RSS items


# ---------- Helpers ----------
def update_env_var(key, value):
    lines = []
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
    updated = False
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}\n"
            updated = True
            break
    if not updated:
        lines.append(f"{key}={value}\n")
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)


def make_embed(title, description, color=discord.Color.blue(), url=None):
    embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.utcnow())
    if url:
        embed.url = url
    embed.set_footer(text="MultiNotify Bot", icon_url="https://www.redditstatic.com/desktop2x/img/favicon/android-icon-192x192.png")
    return embed


def domain_from_url(link: str) -> str:
    try:
        return urlparse(link).netloc or "unknown"
    except Exception:
        return "unknown"


def matches_keywords_text(text: str, keywords_list) -> bool:
    """Generic keyword matcher for plain text using a provided list. Blank list => allow all."""
    if not keywords_list:
        return True
    content = (text or "").lower()
    return any(re.search(rf"\b{re.escape(kw)}\b", content) for kw in keywords_list)


def matches_keywords_post(post, keywords_list) -> bool:
    """Keyword matcher for Reddit posts using provided list. Blank list => allow all."""
    if not keywords_list:
        return True
    content = f"{post.title} {getattr(post, 'selftext', '')}".lower()
    return any(re.search(rf"\b{re.escape(kw)}\b", content) for kw in keywords_list)


async def send_webhook_embed(title, url, description, color=discord.Color.orange()):
    if not WEBHOOK_URL:
        return
    if "discord.com" in WEBHOOK_URL:
        embed = discord.Embed(title=title, url=url, description=description, color=color, timestamp=datetime.utcnow())
        embed.set_footer(text="MultiNotify Bot", icon_url="https://www.redditstatic.com/desktop2x/img/favicon/android-icon-192x192.png")
        try:
            requests.post(WEBHOOK_URL, json={"embeds": [embed.to_dict()]}, timeout=10)
        except Exception as e:
            print(f"[ERROR] Failed to send Discord webhook embed: {e}")
    else:
        # Generic webhook (Slack, etc.)
        msg = f"{title}\n{url}\n{description}"
        try:
            requests.post(WEBHOOK_URL, json={"text": msg}, timeout=10)
        except Exception as e:
            print(f"[ERROR] Failed to send non-Discord webhook: {e}")


async def notify_channels(title, url, description, color=discord.Color.orange()):
    # Send to configured Discord channels via the bot (no webhook)
    if not DISCORD_CHANNEL_IDS:
        return
    embed = discord.Embed(title=title, url=url, description=description, color=color, timestamp=datetime.utcnow())
    embed.set_footer(text="MultiNotify Bot")
    for cid in DISCORD_CHANNEL_IDS:
        try:
            channel = client.get_channel(int(cid))
            if channel is None:
                channel = await client.fetch_channel(int(cid))
            await channel.send(embed=embed)
        except Exception as e:
            print(f"[ERROR] Failed to send to channel {cid}: {e}")


async def notify_dms(message: str):
    if not (ENABLE_DM and DISCORD_USER_IDS):
        return
    for uid in DISCORD_USER_IDS:
        try:
            user = await client.fetch_user(int(uid))
            await user.send(message)
        except Exception as e:
            print(f"[ERROR] Failed to DM {uid}: {e}")


# ---------- Reddit ----------
async def process_reddit():
    global last_post_ids
    subreddit = reddit.subreddit(SUBREDDIT)
    new_posts = []
    for submission in subreddit.new(limit=POST_LIMIT):
        print(f"[DEBUG] Checking post: {submission.title}")

        if ALLOWED_FLAIRS and submission.link_flair_text not in ALLOWED_FLAIRS:
            print(f"[DEBUG] Post skipped due to flair mismatch: {submission.link_flair_text}")
            continue
        if not matches_keywords_post(submission, REDDIT_KEYWORDS):
            print(f"[DEBUG] Post skipped due to keyword mismatch (reddit).")
            continue
        if submission.id in last_post_ids:
            print(f"[DEBUG] Post already seen.")
            continue

        last_post_ids.add(submission.id)
        new_posts.append(submission)

    for post in reversed(new_posts):
        flair = post.link_flair_text if post.link_flair_text else "No Flair"
        post_url = f"https://reddit.com{post.permalink}"
        description = f"Subreddit: r/{SUBREDDIT}\nFlair: **{flair}**\nAuthor: u/{post.author}"

        # Webhook (Discord embed if discord.com)
        await send_webhook_embed(post.title, post_url, description, color=discord.Color.orange())

        # Channels
        await notify_channels(post.title, post_url, description, color=discord.Color.orange())

        # DMs
        if ENABLE_DM and DISCORD_USER_IDS:
            dm_text = f"New post in r/{SUBREDDIT} (Flair: {flair}) by u/{post.author}: {post.title} ({post_url})"
            await notify_dms(dm_text)


# ---------- RSS ----------
async def process_rss():
    global rss_last_ids
    if not RSS_FEEDS:
        return

    fresh_items = []

    for feed_url in RSS_FEEDS:
        try:
            parsed = feedparser.parse(feed_url)
            feed_title = parsed.feed.get("title", domain_from_url(feed_url)) if hasattr(parsed, "feed") else domain_from_url(feed_url)

            count = 0
            for entry in parsed.entries:
                if count >= RSS_LIMIT:
                    break
                entry_id = entry.get("id") or entry.get("link") or f"{entry.get('title','')}-{entry.get('published','')}"
                if not entry_id:
                    continue
                if entry_id in rss_last_ids:
                    continue

                title = entry.get("title", "Untitled")
                link = entry.get("link", feed_url)
                summary = entry.get("summary", "") or entry.get("description", "")
                text_for_match = f"{title}\n{summary}"

                # Use RSS-specific keywords list
                if not matches_keywords_text(text_for_match, RSS_KEYWORDS):
                    continue

                rss_last_ids.add(entry_id)
                fresh_items.append({
                    "feed_title": feed_title,
                    "title": title,
                    "link": link,
                    "summary": summary
                })
                count += 1

        except Exception as e:
            print(f"[ERROR] Failed to parse RSS feed {feed_url}: {e}")

    # Send in chronological order (oldest first)
    for item in reversed(fresh_items):
        feed_title = item["feed_title"]
        title = item["title"]
        link = item["link"]
        summary = item["summary"] or ""
        # Trim summary to keep embeds tidy
        clean_summary = re.sub(r"<[^>]+>", "", summary)  # strip basic HTML
        if len(clean_summary) > 500:
            clean_summary = clean_summary[:497] + "..."

        description = f"Feed: **{feed_title}**\nSource: {domain_from_url(link)}\n\n{clean_summary}"

        # Webhook
        await send_webhook_embed(title, link, description, color=discord.Color.blurple())

        # Channels
        await notify_channels(title, link, description, color=discord.Color.blurple())

        # DMs
        if ENABLE_DM and DISCORD_USER_IDS:
            dm_text = f"New RSS item from {feed_title}: {title} ({link})"
            await notify_dms(dm_text)


# ---------- Scheduler ----------
async def fetch_and_notify():
    await client.wait_until_ready()
    while not client.is_closed():
        try:
            await process_reddit()
        except Exception as e:
            print(f"[ERROR] Reddit fetch failed: {e}")

        try:
            await process_rss()
        except Exception as e:
            print(f"[ERROR] RSS fetch failed: {e}")

        await asyncio.sleep(CHECK_INTERVAL)


# ---------- Auth ----------
def is_admin(interaction: discord.Interaction):
    return str(interaction.user.id) in ADMIN_USER_IDS


# ---------- Commands ----------
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


@tree.command(name="setpostlimit", description="Set number of Reddit posts to check")
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
    shown = WEBHOOK_URL if WEBHOOK_URL else "None"
    await interaction.response.send_message(embed=make_embed("Webhook Updated", f"Webhook URL set to: `{shown}`", discord.Color.green()), ephemeral=True)


@tree.command(name="setflairs", description="Set allowed Reddit flairs (comma separated)")
async def setflairs(interaction: discord.Interaction, flairs: str = ""):
    if not is_admin(interaction):
        return await interaction.response.send_message(embed=make_embed("Unauthorized", "You are not authorized."), ephemeral=True)
    global ALLOWED_FLAIRS
    ALLOWED_FLAIRS = [f.strip() for f in flairs.split(",") if f.strip()]
    update_env_var("ALLOWED_FLAIR", ",".join(ALLOWED_FLAIRS))
    text = ", ".join(ALLOWED_FLAIRS) if ALLOWED_FLAIRS else "ALL"
    await interaction.response.send_message(embed=make_embed("Flairs Updated", f"Now filtering flairs: {text}", discord.Color.green()), ephemeral=True)


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


@tree.command(name="reloadenv", description="Reload process to pick up .env changes")
async def reloadenv(interaction: discord.Interaction):
    if not is_admin(interaction):
        return await interaction.response.send_message(embed=make_embed("Unauthorized", "You are not authorized."), ephemeral=True)
    await interaction.response.send_message(embed=make_embed("Reloading", "Restarting process to reload environment..."), ephemeral=True)
    os.execv(sys.executable, [sys.executable, __file__])


@tree.command(name="whereenv", description="Show current .env path")
async def whereenv(interaction: discord.Interaction):
    await interaction.response.send_message(embed=make_embed("Environment File", f"`{ENV_FILE}`"), ephemeral=True)


# ---------- Keyword commands ----------
@tree.command(name="setredditkeywords", description="Set/clear keywords for Reddit posts (comma separated, blank for ALL)")
async def setredditkeywords(interaction: discord.Interaction, words: str = ""):
    if not is_admin(interaction):
        return await interaction.response.send_message(embed=make_embed("Unauthorized", "You are not authorized to use this command.", discord.Color.red()), ephemeral=True)
    global REDDIT_KEYWORDS
    REDDIT_KEYWORDS = [w.strip().lower() for w in words.split(",") if w.strip()] if words else []
    update_env_var("REDDIT_KEYWORDS", ",".join(REDDIT_KEYWORDS))
    if REDDIT_KEYWORDS:
        await interaction.response.send_message(embed=make_embed("Reddit Keywords Updated", f"Filtering Reddit by: {', '.join(REDDIT_KEYWORDS)}", discord.Color.green()), ephemeral=True)
    else:
        await interaction.response.send_message(embed=make_embed("Reddit Keywords Cleared", "No keywords set. ALL Reddit posts will be considered.", discord.Color.green()), ephemeral=True)


@tree.command(name="setrsskeywords", description="Set/clear keywords for RSS items (comma separated, blank for ALL)")
async def setrsskeywords(interaction: discord.Interaction, words: str = ""):
    if not is_admin(interaction):
        return await interaction.response.send_message(embed=make_embed("Unauthorized", "You are not authorized to use this command.", discord.Color.red()), ephemeral=True)
    global RSS_KEYWORDS
    RSS_KEYWORDS = [w.strip().lower() for w in words.split(",") if w.strip()] if words else []
    update_env_var("RSS_KEYWORDS", ",".join(RSS_KEYWORDS))
    if RSS_KEYWORDS:
        await interaction.response.send_message(embed=make_embed("RSS Keywords Updated", f"Filtering RSS by: {', '.join(RSS_KEYWORDS)}", discord.Color.green()), ephemeral=True)
    else:
        await interaction.response.send_message(embed=make_embed("RSS Keywords Cleared", "No keywords set. ALL RSS items will be considered.", discord.Color.green()), ephemeral=True)


# Backward compatibility: keep /setkeywords to set BOTH lists at once
@tree.command(name="setkeywords", description="(Legacy) Set/clear keywords for BOTH Reddit and RSS")
async def setkeywords(interaction: discord.Interaction, words: str = ""):
    if not is_admin(interaction):
        return await interaction.response.send_message(embed=make_embed("Unauthorized", "You are not authorized to use this command.", discord.Color.red()), ephemeral=True)
    global REDDIT_KEYWORDS, RSS_KEYWORDS
    new_list = [w.strip().lower() for w in words.split(",") if w.strip()] if words else []
    REDDIT_KEYWORDS = new_list[:]
    RSS_KEYWORDS = new_list[:]
    update_env_var("REDDIT_KEYWORDS", ",".join(REDDIT_KEYWORDS))
    update_env_var("RSS_KEYWORDS", ",".join(RSS_KEYWORDS))
    # Also update legacy KEYWORDS for people reading .env manually
    update_env_var("KEYWORDS", ",".join(new_list))
    label = ", ".join(new_list) if new_list else "ALL"
    await interaction.response.send_message(embed=make_embed("Keywords Updated (Legacy)", f"Reddit & RSS now filter by: {label}", discord.Color.green()), ephemeral=True)


# ---------- Status & Help ----------
@tree.command(name="status", description="Show current monitoring status")
async def status(interaction: discord.Interaction):
    flair_list = ", ".join(ALLOWED_FLAIRS) if ALLOWED_FLAIRS else "ALL"
    dm_status = "enabled" if ENABLE_DM else "disabled"
    webhook_text = WEBHOOK_URL if WEBHOOK_URL else "None"
    dm_users = ", ".join(DISCORD_USER_IDS) if DISCORD_USER_IDS else "None"
    reddit_kw = ", ".join(REDDIT_KEYWORDS) if REDDIT_KEYWORDS else "ALL"
    rss_kw = ", ".join(RSS_KEYWORDS) if RSS_KEYWORDS else "ALL"
    rss_text = "\n".join([f"- {u}" for u in RSS_FEEDS]) if RSS_FEEDS else "None"
    chan_text = ", ".join(DISCORD_CHANNEL_IDS) if DISCORD_CHANNEL_IDS else "None"
    msg = (
        f"Monitoring r/{SUBREDDIT} every **{CHECK_INTERVAL}s**.\n"
        f"Reddit Post limit: **{POST_LIMIT}**.\n"
        f"Flairs: **{flair_list}**.\n"
        f"Reddit Keywords: **{reddit_kw}**.\n"
        f"RSS Keywords: **{rss_kw}**.\n"
        f"DMs: **{dm_status}** (Users: {dm_users}).\n"
        f"Webhook: `{webhook_text}`\n"
        f"Channels: **{chan_text}**\n"
        f"RSS Feeds:\n{rss_text}"
    )
    await interaction.response.send_message(embed=make_embed("Bot Status", msg), ephemeral=True)


@tree.command(name="help", description="Show help for commands")
async def help_cmd(interaction: discord.Interaction):
    commands_text = "\n".join([
        "/setsubreddit <name>",
        "/setinterval <seconds>",
        "/setpostlimit <number>",
        "/setwebhook <url or blank>",
        "/setflairs [comma separated]",
        "/setredditkeywords [comma separated]",
        "/setrsskeywords [comma separated]",
        "/setkeywords [comma separated]  (legacy: sets both)",
        "/enabledms <true/false>",
        "/adddmuser <user_id>",
        "/removedmuser <user_id>",
        "/addrss <url>",
        "/removerss <url>",
        "/listrss",
        "/addchannel <channel_id>",
        "/removechannel <channel_id>",
        "/listchannels",
        "/status",
        "/reloadenv",
        "/whereenv"
    ])
    await interaction.response.send_message(embed=make_embed("Help", f"**Available Commands:**\n{commands_text}"), ephemeral=True)


# ---------- RSS feed management ----------
@tree.command(name="addrss", description="Add an RSS/Atom feed URL")
async def addrss(interaction: discord.Interaction, url: str):
    if not is_admin(interaction):
        return await interaction.response.send_message(embed=make_embed("Unauthorized", "You are not authorized."), ephemeral=True)
    global RSS_FEEDS
    url = url.strip()
    if url and url not in RSS_FEEDS:
        RSS_FEEDS.append(url)
        update_env_var("RSS_FEEDS", ",".join(RSS_FEEDS))
        await interaction.response.send_message(embed=make_embed("RSS Added", f"Added: {url}", discord.Color.green()), ephemeral=True)
    else:
        await interaction.response.send_message(embed=make_embed("RSS Not Added", "URL empty or already present."), ephemeral=True)


@tree.command(name="removerss", description="Remove an RSS/Atom feed URL")
async def removerss(interaction: discord.Interaction, url: str):
    if not is_admin(interaction):
        return await interaction.response.send_message(embed=make_embed("Unauthorized", "You are not authorized."), ephemeral=True)
    global RSS_FEEDS
    url = url.strip()
    if url in RSS_FEEDS:
        RSS_FEEDS.remove(url)
        update_env_var("RSS_FEEDS", ",".join(RSS_FEEDS))
        await interaction.response.send_message(embed=make_embed("RSS Removed", f"Removed: {url}", discord.Color.green()), ephemeral=True)
    else:
        await interaction.response.send_message(embed=make_embed("Not Found", "That URL isn't in the list."), ephemeral=True)


@tree.command(name="listrss", description="List configured RSS/Atom feed URLs")
async def listrss(interaction: discord.Interaction):
    text = "\n".join([f"- {u}" for u in RSS_FEEDS]) if RSS_FEEDS else "None"
    await interaction.response.send_message(embed=make_embed("RSS Feeds", text), ephemeral=True)


# ---------- Channel management ----------
@tree.command(name="addchannel", description="Add a Discord channel ID for notifications")
async def addchannel(interaction: discord.Interaction, channel_id: str):
    if not is_admin(interaction):
        return await interaction.response.send_message(embed=make_embed("Unauthorized", "You are not authorized."), ephemeral=True)
    global DISCORD_CHANNEL_IDS
    if channel_id not in DISCORD_CHANNEL_IDS:
        DISCORD_CHANNEL_IDS.append(channel_id)
        update_env_var("DISCORD_CHANNEL_IDS", ",".join(DISCORD_CHANNEL_IDS))
        await interaction.response.send_message(embed=make_embed("Channel Added", f"Added channel ID: {channel_id}", discord.Color.green()), ephemeral=True)
    else:
        await interaction.response.send_message(embed=make_embed("No Change", "Channel ID already present."), ephemeral=True)


@tree.command(name="removechannel", description="Remove a Discord channel ID from notifications")
async def removechannel(interaction: discord.Interaction, channel_id: str):
    if not is_admin(interaction):
        return await interaction.response.send_message(embed=make_embed("Unauthorized", "You are not authorized."), ephemeral=True)
    global DISCORD_CHANNEL_IDS
    if channel_id in DISCORD_CHANNEL_IDS:
        DISCORD_CHANNEL_IDS.remove(channel_id)
        update_env_var("DISCORD_CHANNEL_IDS", ",".join(DISCORD_CHANNEL_IDS))
        await interaction.response.send_message(embed=make_embed("Channel Removed", f"Removed channel ID: {channel_id}", discord.Color.green()), ephemeral=True)
    else:
        await interaction.response.send_message(embed=make_embed("Not Found", "That channel ID isn't in the list."), ephemeral=True)


@tree.command(name="listchannels", description="List Discord channel IDs used for notifications")
async def listchannels(interaction: discord.Interaction):
    text = ", ".join(DISCORD_CHANNEL_IDS) if DISCORD_CHANNEL_IDS else "None"
    await interaction.response.send_message(embed=make_embed("Channels", text), ephemeral=True)


# ---------- Discord lifecycle ----------
@client.event
async def on_ready():
    await tree.sync()
    print(f"Logged in as {client.user}")
    client.loop.create_task(fetch_and_notify())


client.run(DISCORD_TOKEN)
