import os
import sys
import praw
import requests
import asyncio
import discord
import re
import feedparser
import json
from pathlib import Path
from discord import app_commands
from datetime import datetime, time
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
from typing import List

# ---------- Timezone (hard switch) ----------
TZ = ZoneInfo("America/Chicago")

def now_local():
    return datetime.now(TZ)

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

# Separate keywords for Reddit vs RSS (legacy KEYWORDS still supported)
LEGACY_KEYWORDS = [k.strip().lower() for k in os.environ.get("KEYWORDS", "").split(",") if k.strip()]
REDDIT_KEYWORDS = [k.strip().lower() for k in os.environ.get("REDDIT_KEYWORDS", "").split(",") if k.strip()] or LEGACY_KEYWORDS
RSS_KEYWORDS = [k.strip().lower() for k in os.environ.get("RSS_KEYWORDS", "").split(",") if k.strip()]

# RSS feeds and channel IDs
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

# ---------- Small persistence (data dir) ----------
DATA_DIR = Path("/app/data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ---------- Seen store (per-destination) ----------
SEEN_PATH = DATA_DIR / "seen.json"

def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception:
        return default

def _ensure_seen_shape(d: dict) -> dict:
    if not isinstance(d, dict):
        d = {}
    d.setdefault("global", {})
    d["global"].setdefault("reddit", [])
    d["global"].setdefault("rss", [])
    d.setdefault("users", {})
    for uid, rec in list(d["users"].items()):
        if not isinstance(rec, dict):
            d["users"][uid] = {"reddit": [], "rss": []}
        else:
            rec.setdefault("reddit", [])
            rec.setdefault("rss", [])
    return d

def load_seen():
    return _ensure_seen_shape(_load_json(SEEN_PATH, {}))

def save_seen(seen):
    try:
        SEEN_PATH.write_text(json.dumps(seen, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[ERROR] Saving seen.json: {e}")

_seen = load_seen()

def _prune_list(lst, limit=5000):
    if len(lst) > limit:
        del lst[:-limit]

def get_global_seen(kind: str) -> set:
    rec = _seen.get("global", {})
    return set(rec.get(kind, []))

def mark_global_seen(kind: str, item_id: str):
    rec = _seen.setdefault("global", {})
    arr = rec.setdefault(kind, [])
    if item_id not in arr:
        arr.append(item_id)
        _prune_list(arr)
        save_seen(_seen)

def get_user_seen(uid: int, kind: str) -> set:
    urec = _seen.setdefault("users", {}).setdefault(str(uid), {"reddit": [], "rss": []})
    return set(urec.get(kind, []))

def mark_user_seen(uid: int, kind: str, item_id: str):
    urec = _seen.setdefault("users", {}).setdefault(str(uid), {"reddit": [], "rss": []})
    arr = urec.setdefault(kind, [])
    if item_id not in arr:
        arr.append(item_id)
        _prune_list(arr)
        save_seen(_seen)

# ---------- Visuals (footer-only icons) ----------
REDDIT_ICON = "https://www.redditstatic.com/desktop2x/img/favicon/android-icon-192x192.png"
RSS_ICON = "https://upload.wikimedia.org/wikipedia/commons/thumb/4/43/Feed-icon.svg/192px-Feed-icon.svg.png"

# ---------- Small persistence for per-user prefs ----------
PREFS_PATH = DATA_DIR / "user_prefs.json"  # { "1234567890": { ... }, ... }
user_prefs = _load_json(PREFS_PATH, {})

def save_prefs():
    try:
        PREFS_PATH.write_text(json.dumps(user_prefs, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[ERROR] Saving prefs: {e}")

def _norm_sub(name: str) -> str:
    name = (name or "").strip().lower()
    if name.startswith("r/"):
        name = name[2:]
    return name

def get_user_prefs(uid: int):
    """Return merged view of global defaults + user overrides."""
    uid = str(uid)
    base = {
        "enable_dm": ENABLE_DM,            # default to global for convenience
        "reddit_keywords": [],             # empty => allow all for personal
        "rss_keywords": [],                # empty => allow all for personal
        "quiet_hours": None,               # {"start":"22:00","end":"07:00"} or None  (America/Chicago)
        "digest": "off",                   # off | daily | weekly
        "digest_time": "09:00",            # HH:MM in America/Chicago
        "digest_day": "mon",               # mon|tue|...|sun
        "preferred_channel_id": None,      # channel to send to instead of DM
        "reddit_flairs": [],               # optional personal flair filter; empty => allow all
        "feeds": [],                       # personal RSS/Atom feed URLs
        "subreddits": []                   # personal subreddit list (names without r/)
    }
    p = {**base, **user_prefs.get(uid, {})}
    p["subreddits"] = [_norm_sub(s) for s in p.get("subreddits", []) if _norm_sub(s)]
    day = (p.get("digest_day") or "mon").lower()
    if day not in ("mon","tue","wed","thu","fri","sat","sun"):
        day = "mon"
    p["digest_day"] = day
    return p

def set_user_pref(uid: int, key: str, value):
    uid = str(uid)
    cur = user_prefs.get(uid, {})
    cur[key] = value
    user_prefs[uid] = cur
    save_prefs()

def is_quiet_now(uid: int):
    """Quiet hours apply ONLY to personal deliveries (global DM list ignores this). Interpreted in America/Chicago."""
    q = get_user_prefs(uid).get("quiet_hours")
    if not q:
        return False
    try:
        sH, sM = map(int, q["start"].split(":"))
        eH, eM = map(int, q["end"].split(":"))
        now_t = now_local().time()
        start, end = time(sH, sM), time(eH, eM)
        return (start <= now_t < end) if start < end else (now_t >= start or now_t < end)
    except Exception:
        return False

# ---------- Digest helpers ----------
DIGEST_QUEUE_PATH = DATA_DIR / "digests.json"     # { uid: [ {type, title, link, meta..., ts} ] }
DIGEST_META_PATH  = DATA_DIR / "digest_meta.json" # { uid: {"daily_last":"YYYY-MM-DD","weekly_last":"YYYY-WW"} }

def _load_digests():
    data = _load_json(DIGEST_QUEUE_PATH, {})
    return data if isinstance(data, dict) else {}

def _save_digests(d):
    try:
        DIGEST_QUEUE_PATH.write_text(json.dumps(d, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[ERROR] Saving digests: {e}")

def _load_digest_meta():
    data = _load_json(DIGEST_META_PATH, {})
    return data if isinstance(data, dict) else {}

def _save_digest_meta(d):
    try:
        DIGEST_META_PATH.write_text(json.dumps(d, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[ERROR] Saving digest meta: {e}")

def queue_digest_item(uid: int, item: dict):
    q = _load_digests()
    arr = q.get(str(uid), [])
    arr.append(item)
    q[str(uid)] = arr
    _save_digests(q)

def pop_all_digest_items(uid: int):
    q = _load_digests()
    arr = q.get(str(uid), [])
    q[str(uid)] = []
    _save_digests(q)
    return arr

def weekday_index(day: str) -> int:
    mapping = {"mon":0,"tue":1,"wed":2,"thu":3,"fri":4,"sat":5,"sun":6}
    return mapping.get(day.lower(), 0)

def should_send_digest(uid: int) -> bool:
    p = get_user_prefs(uid)
    mode = p.get("digest","off")
    if mode == "off":
        return False

    hh, mm = (p.get("digest_time","09:00") or "09:00").split(":")
    hh, mm = int(hh), int(mm)
    now = now_local()
    due_today = (now.hour == hh and now.minute >= mm)

    meta = _load_digest_meta()
    rec = meta.get(str(uid), {})
    if mode == "daily":
        last = rec.get("daily_last", "")  # "YYYY-MM-DD" in America/Chicago
        today = now.strftime("%Y-%m-%d")
        return due_today and last != today
    if mode == "weekly":
        if now.weekday() != weekday_index(p.get("digest_day","mon")) or not due_today:
            return False
        iso_year, iso_week, _ = now.isocalendar()
        key = f"{iso_year}-{iso_week:02d}"
        last = rec.get("weekly_last","")
        return last != key
    return False

def mark_digest_sent(uid: int):
    p = get_user_prefs(uid)
    mode = p.get("digest","off")
    if mode == "off":
        return
    now = now_local()
    meta = _load_digest_meta()
    rec = meta.get(str(uid), {})
    if mode == "daily":
        rec["daily_last"] = now.strftime("%Y-%m-%d")
    elif mode == "weekly":
        iso_year, iso_week, _ = now.isocalendar()
        rec["weekly_last"] = f"{iso_year}-{iso_week:02d}"
    meta[str(uid)] = rec
    _save_digest_meta(meta)

# ---------- Utils ----------
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
    # Timestamp shown as local time for readability
    embed = discord.Embed(title=title, description=description, color=color, timestamp=now_local())
    if url:
        embed.url = url
    embed.set_footer(text="MultiNotify Bot")
    return embed

def domain_from_url(link: str) -> str:
    try:
        return urlparse(link).netloc or "unknown"
    except Exception:
        return "unknown"

def matches_keywords_text(text: str, keywords_list) -> bool:
    if not keywords_list:
        return True
    content = (text or "").lower()
    return any(re.search(rf"\b{re.escape(kw)}\b", content) for kw in keywords_list)

def matches_keywords_post(post, keywords_list) -> bool:
    if not keywords_list:
        return True
    content = f"{post.title} {getattr(post, 'selftext', '')}".lower()
    return any(re.search(rf"\b{re.escape(kw)}\b", content) for kw in keywords_list)

def build_source_embed(title, url, description, color, source_type):
    embed = discord.Embed(title=title, url=url, description=description, color=color, timestamp=now_local())
    if source_type == "reddit":
        embed.set_author(name="Reddit")
        embed.set_footer(text="MultiNotify • Reddit", icon_url=REDDIT_ICON)
    elif source_type == "rss":
        embed.set_author(name="RSS Feed")
        embed.set_footer(text="MultiNotify • RSS", icon_url=RSS_ICON)
    else:
        embed.set_footer(text="MultiNotify")
    return embed

async def send_webhook_embed(title, url, description, color, source_type):
    if not WEBHOOK_URL:
        return
    if "discord.com" in WEBHOOK_URL:
        embed = build_source_embed(title, url, description, color, source_type)
        try:
            requests.post(WEBHOOK_URL, json={"embeds": [embed.to_dict()]}, timeout=10)
        except Exception as e:
            print(f"[ERROR] Failed to send Discord webhook embed: {e}")
    else:
        prefix = "[Reddit]" if source_type == "reddit" else "[RSS]"
        msg = f"{prefix} {title}\n{url}\n{description}"
        try:
            requests.post(WEBHOOK_URL, json={"text": msg}, timeout=10)
        except Exception as e:
            print(f"[ERROR] Failed to send non-Discord webhook: {e}")

async def notify_channels(title, url, description, color, source_type):
    if not DISCORD_CHANNEL_IDS:
        return
    embed = build_source_embed(title, url, description, color, source_type)
    for cid in DISCORD_CHANNEL_IDS:
        try:
            channel = client.get_channel(int(cid))
            if channel is None:
                channel = await client.fetch_channel(int(cid))
            await channel.send(embed=embed)
        except Exception as e:
            print(f"[ERROR] Failed to send to channel {cid}: {e}")

async def notify_dms(message: str):
    """GLOBAL DM LIST: this intentionally ignores quiet hours."""
    if not (ENABLE_DM and DISCORD_USER_IDS):
        return
    for uid in DISCORD_USER_IDS:
        try:
            user = await client.fetch_user(int(uid))
            await user.send(message)
        except Exception as e:
            print(f"[ERROR] Failed to DM {uid}: {e}")

# ---------- Helpers to compute unions ----------
def union_user_subreddits():
    subs = {_norm_sub(SUBREDDIT)} if SUBREDDIT and _norm_sub(SUBREDDIT) else set()
    for p in user_prefs.values():
        for s in p.get("subreddits", []):
            if s:
                subs.add(_norm_sub(s))
    return subs

def union_user_feeds():
    feeds = set(RSS_FEEDS)
    for p in user_prefs.values():
        for u in p.get("feeds", []):
            if u:
                feeds.add(u.strip())
    return feeds

# ---------- Reddit ----------
async def process_reddit():
    # Build union of subreddits to fetch for PERSONAL pipeline
    union_subs = union_user_subreddits()
    # If no subs anywhere, skip reddit entirely
    if not union_subs:
        return

    global_posts = []    # pass global filters from the global SUBREDDIT only (if defined)
    personal_posts = []  # (post, sub_name) from ANY union subreddit

    for sub_name in union_subs:
        try:
            sr = reddit.subreddit(sub_name)
            for submission in sr.new(limit=POST_LIMIT):
                # Collect for personal route
                personal_posts.append((submission, sub_name))

                # Global route only if SUBREDDIT is set and matches
                if SUBREDDIT and sub_name == _norm_sub(SUBREDDIT):
                    flair_ok = (not ALLOWED_FLAIRS) or (submission.link_flair_text in ALLOWED_FLAIRS)
                    kw_ok = matches_keywords_post(submission, REDDIT_KEYWORDS)
                    if flair_ok and kw_ok:
                        global_posts.append(submission)
        except Exception as e:
            print(f"[ERROR] Fetch subreddit r/{sub_name}: {e}")

    # ---------- GLOBAL DELIVERY ----------
    if SUBREDDIT:
        for post in reversed(global_posts):
            if post.id in get_global_seen("reddit"):
                continue
            flair = post.link_flair_text if post.link_flair_text else "No Flair"
            post_url = f"https://reddit.com{post.permalink}"
            description = f"Subreddit: r/{_norm_sub(SUBREDDIT)}\nFlair: **{flair}**\nAuthor: u/{post.author}"

            await send_webhook_embed(post.title, post_url, description, color=discord.Color.orange(), source_type="reddit")
            await notify_channels(post.title, post_url, description, color=discord.Color.orange(), source_type="reddit")

            # Mark global seen
            mark_global_seen("reddit", post.id)

            # Global DM list — deliberately IGNORE quiet hours
            if ENABLE_DM and DISCORD_USER_IDS:
                dm_text = f"[Reddit] r/{_norm_sub(SUBREDDIT)} • Flair: {flair} • u/{post.author}\n{post.title}\n{post_url}"
                await notify_dms(dm_text)

    # ---------- PERSONAL DELIVERY ----------
    if user_prefs:
        for post, sub_name in reversed(personal_posts):
            post_url = f"https://reddit.com{post.permalink}"
            flair = post.link_flair_text or "No Flair"
            sub_name_l = _norm_sub(sub_name)

            for uid_str in list(user_prefs.keys()):
                uid = int(uid_str)
                p = get_user_prefs(uid)

                # Determine which subreddits this user wants:
                user_subs = p.get("subreddits", [])
                if user_subs:
                    if sub_name_l not in set(user_subs):
                        continue
                else:
                    # If user hasn't set subs and SUBREDDIT cleared, skip personal delivery
                    if not SUBREDDIT or sub_name_l != _norm_sub(SUBREDDIT):
                        continue

                # Personal matching: keywords/flairs (optional). If none set → allow all.
                p_keywords = p.get("reddit_keywords", [])
                if p_keywords and not matches_keywords_post(post, p_keywords):
                    continue
                p_flairs = p.get("reddit_flairs", [])
                if p_flairs and flair not in p_flairs:
                    continue

                # Quiet hours apply ONLY to personal route
                if is_quiet_now(uid):
                    continue

                # Per-user seen check
                if post.id in get_user_seen(uid, "reddit"):
                    continue

                # Digest path
                if p.get("digest","off") != "off":
                    queue_digest_item(uid, {
                        "type": "reddit",
                        "title": post.title,
                        "link": post_url,
                        "subreddit": sub_name_l,
                        "flair": flair,
                        "author": str(post.author) if post.author else "unknown",
                        "ts": now_local().isoformat(timespec="seconds")
                    })
                    mark_user_seen(uid, "reddit", post.id)
                    continue

                # Immediate delivery
                try:
                    embed = build_source_embed(
                        post.title,
                        post_url,
                        f"Subreddit: r/{sub_name_l}\nFlair: **{flair}**\nAuthor: u/{post.author}",
                        color=discord.Color.orange(),
                        source_type="reddit"
                    )
                    if p.get("preferred_channel_id"):
                        ch = client.get_channel(int(p["preferred_channel_id"])) or await client.fetch_channel(int(p["preferred_channel_id"]))
                        await ch.send(embed=embed)
                    elif p.get("enable_dm"):
                        user = await client.fetch_user(uid)
                        await user.send(embed=embed)
                    mark_user_seen(uid, "reddit", post.id)
                except Exception as e:
                    print(f"[ERROR] Personal delivery to {uid}: {e}")

# ---------- RSS ----------
async def process_rss():
    # Build union of feeds for PERSONAL fetch; global still uses RSS_FEEDS for global pipeline
    feeds_union = union_user_feeds()
    if not feeds_union:
        feeds_union = set(RSS_FEEDS)

    global_items = []    # pass global RSS keywords from GLOBAL feeds
    personal_items = []  # items from ANY union feed

    for feed_url in feeds_union:
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

                title = entry.get("title", "Untitled")
                link = entry.get("link", feed_url)
                summary = entry.get("summary", "") or entry.get("description", "")
                text_for_match = f"{title}\n{summary}"

                # Always consider for personal route (store feed_url)
                personal_items.append({
                    "feed_title": feed_title,
                    "title": title,
                    "link": link,
                    "summary": summary,
                    "id": entry_id,
                    "feed_url": feed_url
                })

                # Global route uses global RSS_KEYWORDS but only for global feeds
                if feed_url in RSS_FEEDS and matches_keywords_text(text_for_match, RSS_KEYWORDS):
                    global_items.append({
                        "feed_title": feed_title,
                        "title": title,
                        "link": link,
                        "summary": summary,
                        "id": entry_id,
                        "feed_url": feed_url
                    })

                count += 1

        except Exception as e:
            print(f"[ERROR] Failed to parse RSS feed {feed_url}: {e}")

    # ---------- GLOBAL DELIVERY ----------
    for item in reversed(global_items):
        if item["id"] in get_global_seen("rss"):
            continue
        feed_title = item["feed_title"]
        title = item["title"]
        link = item["link"]
        summary = item["summary"] or ""
        clean_summary = re.sub(r"<[^>]+>", "", summary)
        if len(clean_summary) > 500:
            clean_summary = clean_summary[:497] + "..."

        description = f"Feed: **{feed_title}**\nSource: {domain_from_url(link)}\n\n{clean_summary}"

        await send_webhook_embed(title, link, description, color=discord.Color.blurple(), source_type="rss")
        await notify_channels(title, link, description, color=discord.Color.blurple(), source_type="rss")

        # Mark global seen
        mark_global_seen("rss", item["id"])

        # Global DM list — deliberately IGNORE quiet hours
        if ENABLE_DM and DISCORD_USER_IDS:
            dm_text = f"[RSS] {feed_title}\n{title}\n{link}"
            await notify_dms(dm_text)

    # ---------- PERSONAL DELIVERY ----------
    if user_prefs:
        for item in reversed(personal_items):
            feed_title = item["feed_title"]
            title = item["title"]
            link = item["link"]
            summary = item["summary"] or ""
            clean_summary = re.sub(r"<[^>]+>", "", summary)
            if len(clean_summary) > 500:
                clean_summary = clean_summary[:497] + "..."
            description = f"Feed: **{feed_title}**\nSource: {domain_from_url(link)}\n\n{clean_summary}"

            text_for_match = f"{title}\n{summary}"
            feed_url = item["feed_url"]

            for uid_str in list(user_prefs.keys()):
                uid = int(uid_str)
                p = get_user_prefs(uid)

                # User must be subscribed to the feed to receive personal delivery
                user_feeds = [u.strip() for u in p.get("feeds", []) if u.strip()]
                if user_feeds and feed_url not in user_feeds:
                    continue
                if not user_feeds:
                    # If they haven't added any feeds, don't deliver personal RSS to avoid spam
                    continue

                # Personal keywords for RSS (empty => allow all)
                p_rss_kw = p.get("rss_keywords", [])
                if p_rss_kw and not matches_keywords_text(text_for_match, p_rss_kw):
                    continue

                if is_quiet_now(uid):
                    continue

                # Per-user seen check
                if item["id"] in get_user_seen(uid, "rss"):
                    continue

                if p.get("digest","off") != "off":
                    queue_digest_item(uid, {
                        "type": "rss",
                        "title": title,
                        "link": link,
                        "feed_title": feed_title,
                        "ts": now_local().isoformat(timespec="seconds")
                    })
                    mark_user_seen(uid, "rss", item["id"])
                    continue

                try:
                    embed = build_source_embed(title, link, description, color=discord.Color.blurple(), source_type="rss")
                    if p.get("preferred_channel_id"):
                        ch = client.get_channel(int(p["preferred_channel_id"])) or await client.fetch_channel(int(p["preferred_channel_id"]))
                        await ch.send(embed=embed)
                    elif p.get("enable_dm"):
                        user = await client.fetch_user(uid)
                        await user.send(embed=embed)
                    mark_user_seen(uid, "rss", item["id"])
                except Exception as e:
                    print(f"[ERROR] Personal RSS delivery to {uid}: {e}")

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

async def digest_scheduler():
    await client.wait_until_ready()
    while not client.is_closed():
        try:
            for uid_str in list(user_prefs.keys()):
                uid = int(uid_str)
                p = get_user_prefs(uid)
                if p.get("digest","off") == "off":
                    continue
                if not should_send_digest(uid):
                    continue

                items = pop_all_digest_items(uid)
                if not items:
                    mark_digest_sent(uid)
                    continue

                # Destination
                dest_channel_id = p.get("preferred_channel_id")
                dest_user = None
                dest_channel = None
                try:
                    if dest_channel_id:
                        dest_channel = client.get_channel(int(dest_channel_id)) or await client.fetch_channel(int(dest_channel_id))
                    else:
                        dest_user = await client.fetch_user(uid)
                except Exception as e:
                    print(f"[ERROR] Resolving destination for {uid}: {e}")
                    continue

                # Build chunks
                def format_line(it):
                    if it.get("type") == "reddit":
                        sub = it.get("subreddit","?")
                        return f"• [Reddit] r/{sub} — {it.get('title','(no title)')}\n{it.get('link','')}"
                    else:
                        feed = it.get("feed_title","Feed")
                        return f"• [RSS] {feed} — {it.get('title','(no title)')}\n{it.get('link','')}"

                lines = [format_line(it) for it in items]
                CHUNK = 20
                chunks = [lines[i:i+CHUNK] for i in range(0, len(lines), CHUNK)]

                for idx, block in enumerate(chunks, start=1):
                    desc = "\n".join(block)
                    title = "Your Daily Digest" if p.get("digest") == "daily" else f"Your Weekly Digest ({p.get('digest_day').capitalize()})"
                    title = f"{title} — Part {idx}/{len(chunks)}" if len(chunks) > 1 else title
                    embed = make_embed(title, desc, discord.Color.gold())

                    try:
                        if dest_channel:
                            await dest_channel.send(embed=embed)
                        elif dest_user:
                            await dest_user.send(embed=embed)
                    except Exception as e:
                        print(f"[ERROR] Sending digest to {uid}: {e}")

                mark_digest_sent(uid)
        except Exception as e:
            print(f"[ERROR] digest_scheduler: {e}")

        await asyncio.sleep(60)

# ---------- Auth ----------
def is_admin(interaction: discord.Interaction):
    return str(interaction.user.id) in ADMIN_USER_IDS

# ---------- Admin Commands (GLOBAL) ----------
@tree.command(name="setsubreddit", description="Set subreddit to monitor (blank to clear)")
async def setsubreddit(interaction: discord.Interaction, name: str = ""):
    if not is_admin(interaction):
        return await interaction.response.send_message(embed=make_embed("Unauthorized", "You are not authorized."), ephemeral=True)
    global SUBREDDIT
    if not name.strip():
        SUBREDDIT = ""
        update_env_var("SUBREDDIT", "")
        return await interaction.response.send_message(embed=make_embed("Subreddit Cleared", "No subreddit is currently being monitored."), ephemeral=True)
    SUBREDDIT = _norm_sub(name.strip())
    update_env_var("SUBREDDIT", SUBREDDIT)
    await interaction.response.send_message(embed=make_embed("Subreddit Updated", f"Now monitoring r/{SUBREDDIT}", discord.Color.green()), ephemeral=True)

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

@tree.command(name="setflairs", description="Set allowed Reddit flairs (comma separated, blank to clear)")
async def setflairs(interaction: discord.Interaction, flairs: str = ""):
    if not is_admin(interaction):
        return await interaction.response.send_message(embed=make_embed("Unauthorized", "You are not authorized."), ephemeral=True)
    global ALLOWED_FLAIRS
    if not flairs.strip():
        ALLOWED_FLAIRS = []
        update_env_var("ALLOWED_FLAIR", "")
        return await interaction.response.send_message(embed=make_embed("Flairs Cleared", "No flair filter is now set — all flairs allowed."), ephemeral=True)
    ALLOWED_FLAIRS = [f.strip() for f in flairs.split(",") if f.strip()]
    update_env_var("ALLOWED_FLAIR", ",".join(ALLOWED_FLAIRS))
    text = ", ".join(ALLOWED_FLAIRS)
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

# ---------- Keyword commands (GLOBAL) ----------
@tree.command(name="setredditkeywords", description="Set/clear keywords for Reddit posts (comma separated, blank for ALL)")
async def setredditkeywords(interaction: discord.Interaction, words: str = ""):
    if not is_admin(interaction):
        return await interaction.response.send_message(embed=make_embed("Unauthorized", "You are not authorized to use this command.", discord.Color.red()), ephemeral=True)
    global REDDIT_KEYWORDS
    REDDIT_KEYWORDS = [w.strip().lower() for w in words.split(",") if w.strip()] if words else []
    update_env_var("REDDIT_KEYWORDS", ",".join(REDDIT_KEYWORDS))
    if REDDIT_KEYWORDS:
        await interaction.response.send_message(embed=make_embed("Reddit Keywords Updated", f"Filtering Reddit by: {', '.join(REDDIT_KEYWORDS)}"), ephemeral=True)
    else:
        await interaction.response.send_message(embed=make_embed("Reddit Keywords Cleared", "No keywords set. ALL Reddit posts will be considered."), ephemeral=True)

@tree.command(name="setrsskeywords", description="Set/clear keywords for RSS items (comma separated, blank for ALL)")
async def setrsskeywords(interaction: discord.Interaction, words: str = ""):
    if not is_admin(interaction):
        return await interaction.response.send_message(embed=make_embed("Unauthorized", "You are not authorized to use this command.", discord.Color.red()), ephemeral=True)
    global RSS_KEYWORDS
    RSS_KEYWORDS = [w.strip().lower() for w in words.split(",") if w.strip()] if words else []
    update_env_var("RSS_KEYWORDS", ",".join(RSS_KEYWORDS))
    if RSS_KEYWORDS:
        await interaction.response.send_message(embed=make_embed("RSS Keywords Updated", f"Filtering RSS by: {', '.join(RSS_KEYWORDS)}"), ephemeral=True)
    else:
        await interaction.response.send_message(embed=make_embed("RSS Keywords Cleared", "No keywords set. ALL RSS items will be considered."), ephemeral=True)

# Legacy: set BOTH lists at once
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
    update_env_var("KEYWORDS", ",".join(new_list))  # keep legacy env in sync
    label = ", ".join(new_list) if new_list else "ALL"
    await interaction.response.send_message(embed=make_embed("Keywords Updated (Legacy)", f"Reddit & RSS now filter by: {label}"), ephemeral=True)

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
    sub_text = f"r/{_norm_sub(SUBREDDIT)}" if SUBREDDIT else "None"
    msg = (
        f"Monitoring: **{sub_text}** every **{CHECK_INTERVAL}s**.\n"
        f"Reddit Post limit: **{POST_LIMIT}**.\n"
        f"Flairs: **{flair_list}**.\n"
        f"Reddit Keywords (GLOBAL): **{reddit_kw}**.\n"
        f"RSS Keywords (GLOBAL): **{rss_kw}**.\n"
        f"DMs (GLOBAL): **{dm_status}** (Users: {dm_users}).\n"
        f"Webhook: `{webhook_text}`\n"
        f"Channels: **{chan_text}**\n"
        f"RSS Feeds:\n{rss_text}\n"
        f"Time zone: **America/Chicago**"
    )
    await interaction.response.send_message(embed=make_embed("Bot Status", msg), ephemeral=True)

@tree.command(name="help", description="Show help for commands")
async def help_cmd(interaction: discord.Interaction):
    commands_text = "\n".join([
        "Admin (global):",
        "/setsubreddit <name or blank>",
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
        "/whereenv",
        "",
        "Personal (any user):",
        "/myprefs",
        "/setmydms <true/false>",
        "/setmykeywords reddit:<csv> rss:<csv>",
        "/setmyflairs [comma separated]",
        "/setquiet <start HH:MM> <end HH:MM>   (America/Chicago)",
        "/quietoff",
        "/setchannel <channel_id or blank>",
        "/myfeeds add <url> | remove <url> | list",
        "/mysubs add <subreddit> | remove <subreddit> | list",
        "/setdigest <off|daily|weekly> [HH:MM] [day(mon..sun)]   (America/Chicago)"
    ])
    await interaction.response.send_message(embed=make_embed("Help", f"**Available Commands:**\n{commands_text}"), ephemeral=True)

# ---------- Personal commands (ANY USER) ----------
@tree.command(name="myprefs", description="Show your personal notification settings")
async def myprefs(interaction: discord.Interaction):
    p = get_user_prefs(interaction.user.id)
    desc = (
        f"DMs: **{'on' if p['enable_dm'] else 'off'}**\n"
        f"Reddit keywords: **{', '.join(p['reddit_keywords']) or 'ALL'}**\n"
        f"RSS keywords: **{', '.join(p['rss_keywords']) or 'ALL'}**\n"
        f"Personal flairs: **{', '.join(p['reddit_flairs']) or 'ALL'}**\n"
        f"Quiet hours (America/Chicago): **{p['quiet_hours'] or 'off'}**\n"
        f"Digest: **{p['digest']}** at **{p['digest_time']}**{' on **'+p['digest_day']+'**' if p['digest']=='weekly' else ''} (America/Chicago)\n"
        f"Preferred channel: **{p['preferred_channel_id'] or 'DMs'}**\n"
        f"Personal feeds: **{len(p['feeds'])}**\n"
        f"Personal subreddits: **{len(p['subreddits'])}**"
    )
    await interaction.response.send_message(embed=make_embed("Your Preferences", desc), ephemeral=True)

@tree.command(name="setmydms", description="Enable or disable your personal DMs")
async def setmydms(interaction: discord.Interaction, value: bool):
    set_user_pref(interaction.user.id, "enable_dm", value)
    await interaction.response.send_message(
        embed=make_embed("Updated", f"DMs {'enabled' if value else 'disabled'} for you"),
        ephemeral=True
    )

@tree.command(name="setmykeywords", description="Set your personal keywords. Example: reddit:docker,proxmox rss:self-hosted")
async def setmykeywords(interaction: discord.Interaction, reddit: str = "", rss: str = ""):
    changed = []
    if reddit is not None:
        rlist = [w.strip().lower() for w in reddit.split(",") if w.strip()]
        set_user_pref(interaction.user.id, "reddit_keywords", rlist)
        changed.append("Reddit")
    if rss is not None:
        rlist = [w.strip().lower() for w in rss.split(",") if w.strip()]
        set_user_pref(interaction.user.id, "rss_keywords", rlist)
        changed.append("RSS")
    label = ", ".join(changed) if changed else "none"
    await interaction.response.send_message(embed=make_embed("Updated", f"Personal keywords saved ({label})."), ephemeral=True)

@tree.command(name="setmyflairs", description="Set your personal allowed Reddit flairs (comma separated, blank for ALL)")
async def setmyflairs(interaction: discord.Interaction, flairs: str = ""):
    # Normalize input into a list
    flair_list = [f.strip() for f in (flairs or "").split(",") if f.strip()] if flairs else []
    set_user_pref(interaction.user.id, "reddit_flairs", flair_list)
    if flair_list:
        await interaction.response.send_message(
            embed=make_embed("Personal Flairs Updated", f"Now filtering Reddit by: {', '.join(flair_list)}"),
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            embed=make_embed("Personal Flairs Cleared", "No flair filter set — ALL flairs allowed for you."),
            ephemeral=True
        )

@tree.command(name="setquiet", description="Set quiet hours (America/Chicago). Example: 22:00 07:00")
async def setquiet(interaction: discord.Interaction, start: str, end: str):
    set_user_pref(interaction.user.id, "quiet_hours", {"start": start, "end": end})
    await interaction.response.send_message(embed=make_embed("Updated", f"Quiet hours set: {start}–{end} (America/Chicago)"), ephemeral=True)

@tree.command(name="quietoff", description="Disable your quiet hours")
async def quietoff(interaction: discord.Interaction):
    set_user_pref(interaction.user.id, "quiet_hours", None)
    await interaction.response.send_message(embed=make_embed("Updated", "Quiet hours disabled."), ephemeral=True)

@tree.command(name="setchannel", description="Send your notifications to a specific channel instead of DMs (blank to revert to DMs)")
async def setchannel(interaction: discord.Interaction, channel_id: str = ""):
    set_user_pref(interaction.user.id, "preferred_channel_id", channel_id or None)
    where = f"channel {channel_id}" if channel_id else "DMs"
    await interaction.response.send_message(embed=make_embed("Updated", f"Personal delivery set to {where}"), ephemeral=True)

# ---- Personal RSS feed management ----
@tree.command(name="myfeeds", description="Manage your personal RSS feeds: add/remove/list")
async def myfeeds(interaction: discord.Interaction, action: str, url: str = ""):
    action = (action or "").strip().lower()
    p = get_user_prefs(interaction.user.id)
    feeds = [u.strip() for u in p.get("feeds", []) if u.strip()]

    if action == "list":
        text = "\n".join([f"- {u}" for u in feeds]) if feeds else "You have no personal feeds. Use `/myfeeds add <url>`."
        return await interaction.response.send_message(embed=make_embed("Your RSS Feeds", text), ephemeral=True)

    if action == "add":
        url = (url or "").strip()
        if not url:
            return await interaction.response.send_message(embed=make_embed("Need URL", "Usage: `/myfeeds add <url>`"), ephemeral=True)
        if url not in feeds:
            feeds.append(url)
            set_user_pref(interaction.user.id, "feeds", feeds)
            return await interaction.response.send_message(embed=make_embed("Feed Added", f"Added: {url}"), ephemeral=True)
        else:
            return await interaction.response.send_message(embed=make_embed("No Change", "That URL is already in your list."), ephemeral=True)

    if action == "remove":
        url = (url or "").strip()
        if not url:
            return await interaction.response.send_message(embed=make_embed("Need URL", "Usage: `/myfeeds remove <url>`"), ephemeral=True)
        if url in feeds:
            feeds.remove(url)
            set_user_pref(interaction.user.id, "feeds", feeds)
            return await interaction.response.send_message(embed=make_embed("Feed Removed", f"Removed: {url}"), ephemeral=True)
        else:
            return await interaction.response.send_message(embed=make_embed("Not Found", "That URL isn't in your list."), ephemeral=True)

    await interaction.response.send_message(embed=make_embed("Invalid Action", "Use: `/myfeeds add <url>`, `/myfeeds remove <url>`, or `/myfeeds list`"), ephemeral=True)

# ---- Personal digest management with day choices + time autocomplete ----
DAY_CHOICES = [
    app_commands.Choice(name="Mon", value="mon"),
    app_commands.Choice(name="Tue", value="tue"),
    app_commands.Choice(name="Wed", value="wed"),
    app_commands.Choice(name="Thu", value="thu"),
    app_commands.Choice(name="Fri", value="fri"),
    app_commands.Choice(name="Sat", value="sat"),
    app_commands.Choice(name="Sun", value="sun"),
]

@tree.command(name="setdigest", description="Set your digest: off|daily|weekly [HH:MM] [day] (America/Chicago)")
@app_commands.describe(mode="off | daily | weekly", time_chi="HH:MM in America/Chicago", day="Day of week (weekly only)")
@app_commands.choices(day=DAY_CHOICES)
async def setdigest(interaction: discord.Interaction, mode: str, time_chi: str = "", day: app_commands.Choice[str] = None):
    mode = (mode or "").lower()
    if mode not in ("off","daily","weekly"):
        return await interaction.response.send_message(embed=make_embed("Invalid", "Mode must be off, daily, or weekly."), ephemeral=True)

    if mode == "off":
        set_user_pref(interaction.user.id, "digest", "off")
        await interaction.response.send_message(embed=make_embed("Digest Updated", "Digest disabled for you."), ephemeral=True)
        return

    # validate time (America/Chicago)
    t = (time_chi or "09:00").strip()
    try:
        hh, mm = map(int, t.split(":"))
        assert 0 <= hh < 24 and 0 <= mm < 60
    except Exception:
        return await interaction.response.send_message(embed=make_embed("Invalid Time", "Use HH:MM in America/Chicago, e.g., 09:00"), ephemeral=True)

    set_user_pref(interaction.user.id, "digest_time", f"{hh:02d}:{mm:02d}")
    set_user_pref(interaction.user.id, "digest", mode)

    if mode == "weekly":
        dval = (day.value if isinstance(day, app_commands.Choice) and day is not None else "mon")
        set_user_pref(interaction.user.id, "digest_day", dval)
        await interaction.response.send_message(embed=make_embed("Digest Updated", f"Weekly digest set to {t} America/Chicago on {dval}."), ephemeral=True)
    else:
        await interaction.response.send_message(embed=make_embed("Digest Updated", f"Daily digest set to {t} America/Chicago."), ephemeral=True)

@setdigest.autocomplete("time_chi")
async def setdigest_time_autocomplete(interaction: discord.Interaction, current: str):
    current = (current or "").strip()
    pool = [f"{h:02d}:{m:02d}" for h in range(24) for m in (0, 15, 30, 45)]
    # filter by contains; Discord allows max 25 choices
    suggestions = [t for t in pool if current in t][:25]
    return [app_commands.Choice(name=t, value=t) for t in suggestions]

# ---------- Discord lifecycle ----------
@client.event
async def on_ready():
    await tree.sync()
    print(f"Logged in as {client.user}")
    client.loop.create_task(fetch_and_notify())
    client.loop.create_task(digest_scheduler())

client.run(DISCORD_TOKEN)
