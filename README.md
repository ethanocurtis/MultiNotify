# MultiNotify (v1.7 Beta)

![Python](https://img.shields.io/badge/Python-3.8+-blue) ![Discord](https://img.shields.io/badge/Discord-Bot-brightgreen) ![Webhooks](https://img.shields.io/badge/Webhook-Supported-green) ![Mattermost](https://img.shields.io/badge/Mattermost-Compatible-orange) ![Slack](https://img.shields.io/badge/Slack-Compatible-lightgrey) ![DM Mode](https://img.shields.io/badge/DM-Mode%20Supported-purple) ![License: MIT](https://img.shields.io/badge/License-MIT-yellow)

Monitor subreddits **and** RSS/Atom feeds for new content (optionally filtered by flair or separate keyword lists) and automatically send them to Discord, Mattermost, Slack, or other services via webhook or directly to specific Discord channels. Supports **Discord embeds, DM notifications, slash commands, automatic `.env` updates**, and is fully containerized for easy deployment.

> ⏰ **Timezone:** All user-facing times (digests, quiet hours, timestamps shown in embeds) default to **America/Chicago**, and can be changed by an admin via `/settimezone`.

## Table of Contents
- [Features](#features)
- [How It Works](#how-it-works)
- [Global vs Personal Settings](#global-vs-personal-settings)
- [Slash Commands](#slash-commands)
- [Webhook Behavior](#webhook-behavior)
- [How to Use](#how-to-use)
  - [Clone the Repository](#1-clone-the-repository)
  - [Create a Reddit App](#2-create-a-reddit-app)
  - [Set Up the .env File](#3-set-up-your-env-file)
  - [Enable Discord Bot DMs](#4-enable-discord-bot-dms)
  - [Run the Bot](#5-run-the-bot-with-docker)
  - [Multiple Bots](#6-running-multiple-bots)
- [Notes](#notes)
- [Updating the Bot](#updating-the-bot)
- [Support](#support)
- [License](#license)

## Features
- Monitor any subreddit for new posts (global or personal).
- Monitor any number of RSS/Atom feeds (global or personal).
- Separate **keyword filtering** for Reddit and RSS (whole word, case-insensitive).
- Filter Reddit posts by one or multiple **flairs** (case-sensitive), or watch all.
- **Personal flair filtering** per user that can override global flair filters.
- Deliver to **Discord webhooks** (embeds), **Discord channels** (embeds), **Discord threads**, **DMs** (embeds), and **non-Discord webhooks** (plain text).
- Live configuration via **slash commands** with **.env auto-persist** (automatically saved when running as a Discord bot).
- **Quiet hours** (personal) and **per-user digests** (daily/weekly).
- **Quarter-hour time suggestions** for digest time and **day dropdown** for weekly digests.
- **Per-destination “seen” tracking** to prevent duplicate spam while allowing multiple users to follow the same sources independently.
- **Watched Reddit users**: Admin-managed global list **and** per-user personal lists.
- **Watch bypass toggles** (per user) to ignore subreddit, flair, and/or keyword filters.
- **Configurable timezone** via `/settimezone` (IANA timezones supported).
- **Threaded posting** for Discord channels.
- **Keyword-based routing** to specific Discord channels (global/admin only).
- **Flair-based routing** for global Reddit posts.
- **Diagnostic commands** to explain why content was delivered or skipped.
- Fully containerized; easy to run with Docker/Compose.

> ⚙️ All modules (webhooks, channel sends, thread posting, flair filtering, keyword filtering, DMs) can be enabled or disabled independently for both global and personal settings.


## How It Works
MultiNotify periodically checks the configured sources and delivers new content based on both global and personal settings:

1. **Fetching**
   - **Reddit (subreddits):** Monitors the global subreddit (if set) and any personal subreddits set by users.
   - **Reddit (authors):** **New:** Fetches recent posts from the union of **global watched users** and **all users’ personal watched users**.
   - **RSS/Atom:** Monitors all global feeds plus any personal feeds.

2. **Filtering**
   - Posts and feed items can be filtered by flair (Reddit only) and/or keywords (both Reddit and RSS).
   - Filters can be set globally or personally. **Personal flair filters override global flair filters for that user.**
   - **Watched-user alerts:** Per-user toggles decide whether to **bypass** subreddit, flair, and/or keyword filters.

3. **Routing & Delivery**
   - Global settings deliver to webhooks, global channels, and the global DM list.
   - Personal settings deliver to the user’s DM only.
   - **Watched-user posts** are only delivered to users who:
     - personally watch that author **or**
     - are covered by the global watch list (admin)  
     …and then pass that user’s chosen bypass rules & quiet hours/digest.
  - Items may be routed to specific Discord channels based on:
     - **Global keyword routes**
     - **Global Reddit flair routes**
   - If no route matches, items follow the default delivery path.
   - Delivery targets may include Discord channels, threads, DMs, or webhooks.
   - When thread mode is enabled, messages are posted into reusable threads instead of directly into channels.

4. **Seen Handling**
   - **Global seen list:** Shared for global deliveries (webhooks/channels/global DMs).
   - **Per-user seen lists:** Each user has their own list for personal deliveries.

## Global vs Personal Settings
**Global settings** are managed by admins listed in `ADMIN_USER_IDS` and apply by default.  
**Personal settings** can be set by any user and override the global settings for that user.

**Priority:** Personal settings override their global counterparts (e.g., personal subreddits/flairs/keywords take precedence).

If the global subreddit is cleared, global Reddit monitoring pauses. Personal subreddits still work.

**Watched users**
- Admins can define a **global watched-users** list (e.g., high-signal posters).
- Any user can define **their own personal watched-users** list.
- A watched-user post is delivered to a user if the author is in **that user’s personal list** or in the **admin/global list**—then the user’s **watch bypass toggles** decide whether subreddit/flair/keyword filters are applied.

---

# Slash Commands

**Permissions note:**  
- **Global commands** require the caller to be in `ADMIN_USER_IDS`.  
- **Personal commands** can be used by **any user**.

### Global (Admin) Commands
- `/setsubreddit [name]` — Set/clear the global subreddit to monitor.
- `/setinterval <seconds>` — Polling interval for new items.
- `/setpostlimit <number>` — How many Reddit posts to fetch each cycle.
- `/setflairs [flair1, flair2,...]` — Global Reddit flair filter (**case-sensitive**). Blank clears (allow all).
- `/setredditkeywords [kw1, kw2,...]` — Global Reddit keywords. Blank clears (allow all).
- `/setrsskeywords [kw1, kw2,...]` — Global RSS keywords. Blank clears (allow all).
- `/setkeywords [kw1, kw2,...]` — **Legacy:** set the same keywords for both Reddit and RSS.
- `/setwebhook [url]` — Set/clear webhook. Discord webhooks get embeds; others get plain text.
- `/enabledms <true/false>` — Enable/disable global DM notifications.
- `/adddmuser <user_id>` / `/removedmuser <user_id>` — Manage global DM recipients.
- `/setrssfeeds` — Manage global RSS feeds.
- `/addchannel <channel_id>` / `/removechannel <channel_id>` / `/listchannels` — Manage Discord channels for global sends.
- `/adduserwatch <username>` — Add a Reddit author to the global watch list.
- `/removeuserwatch <username>` — Remove from the global watch list.
- `/listuserwatches` — List all globally watched users.
- `/settimezone <IANA_tz>` — Set the default timezone (e.g., `America/Chicago`, `Europe/London`).
- `/setthreadmode <true|false>` — Enable or disable thread mode globally.
- `/setthreadttl <hours>` — How long inactive threads are kept before cleanup.
- `/setglobalkeywordroute reddit|rss <keyword> <channel_id>` — Route global items by keyword.
- `/setglobalflairroute <flair> <channel_id>` — Route global Reddit posts by flair.
- `/status` — Show current configuration (ephemeral).
- `/whyglobal <url>` — Explain global delivery behavior for a specific item.
- `/help` — Show help (ephemeral).
- `/reloadenv` — Reload `.env`.
- `/whereenv` — Show the path to `.env`.
- `/delglobalkeywordroute` — admin only, removes global keyword routes.
- `/listglobalkeywordroutes` — admin only, lists global keyword routes
- `/delglobalflairroute` — admin only, removes global flair routes.
- `/listglobalflairroutes` — admin only, lists global flair routes.

### Personal (Any User) Commands
- `/myprefs` — Show your personal settings.
- `/setmydms <true/false>` — Enable or disable **your** DMs.
- `/setmykeywords reddit:<csv> rss:<csv>` — Set **your** Reddit/RSS keywords. Blank to clear.
- `/setmyflairs [flair1, flair2,...]` — Set **your** Reddit flairs. Blank to allow all.
- `/mysubs add <subreddit> | remove <subreddit> | list` — Manage **your** subreddits.
- `/myfeeds add <url> | remove <url> | list` — Manage **your** RSS/Atom feeds.
- `/setchannel [channel_id]` — **Deprecated:** command remains available but no longer changes delivery behavior to prevent spam attemps.
- `/setdigest mode:<off|daily|weekly> [time_chi:HH:MM] [day:mon..sun]` —  
  Set your digest:
  - `mode` chooses off/daily/weekly.
  - `time_chi` has **quarter-hour suggestions** (00:00, 00:15, …, 23:45) in the bot’s timezone.
  - `day` is a **dropdown** when `mode=weekly`.
  - Default time if omitted: **09:00**.
- `/setquiet <start HH:MM> <end HH:MM>` — Set your quiet hours in the bot’s timezone (suppresses personal deliveries during that window).
- `/quietoff` — Disable your quiet hours.
- `/mywatch add <username>` — Add a **personal** watched user (no `u/` needed).
- `/mywatch remove <username>` — Remove from your personal watched list.
- `/mywatch list` — List your personal watched users.
- `/mywatchprefs subs:<true|false> flairs:<true|false> keywords:<true|false>` —  
  Control how watched-user alerts are filtered for **you**:
  - `subs:true` (default) → deliver from any subreddit; `false` → only if in your `/mysubs`.
  - `flairs:true` (default) → ignore your `/setmyflairs`; `false` → must match your flairs.
  - `keywords:false` (default) → must match your `/setmykeywords`; `true` → ignore your keywords.
- `/setmythreadmode on|off|default` — Override global thread mode for your personal deliveries.
- `/setkeywordroute reddit|rss <keyword> <channel_id>` — ~~Route your personal notifications by keyword.~~(Currently Disabled to prevent spam)
- `/listkeywordroutes` — ~~List your personal keyword routing rules.~~(Currently Disabled to prevent spam)
- `/why <url>` — Explain why you did or didn’t receive a notification.
- `/whyexpected <url>` — Show blockers first with suggested fixes.

---

## Webhook Behavior
Discord webhooks get embeds; non-Discord webhooks (Slack, Mattermost, etc.) get plain text for compatibility.

- **Discord webhooks** use embeds:
  - Source (Subreddit or Feed title)
  - Flair (Reddit) or Source domain (RSS)
  - Author (Reddit)
  - Title (linked)
  - Branding icons
- **Non-Discord webhooks** (Slack, Mattermost, etc.) use plain text.
- **DM notifications** include source, flair/feed name, author (if Reddit), title, and a link.
- **Channel sends** use the same embed style as Discord webhooks, but sent by the bot.

---

## How to Use

### 1. Clone the Repository
```bash
git clone https://github.com/ethanocurtis/MultiNotify.git
cd MultiNotify
```

### 2. Create a Reddit App
1. Go to https://www.reddit.com/prefs/apps
2. Under **Developed Applications**, click **create app**.
3. Fill in:
   - **Name**: `multinotify`
   - **Type**: `script`
   - **Redirect URI**: `http://localhost`
4. Copy the `client_id` and `client_secret`.

### 3. Set Up Your .env File
Copy and edit `.env.example`:
```bash
cp .env.example .env
```
Example:
```env
REDDIT_CLIENT_ID=your_client_id_here
REDDIT_CLIENT_SECRET=your_client_secret_here
REDDIT_USER_AGENT=multinotify-bot by u/yourusername

SUBREDDIT=asubreddit
ALLOWED_FLAIR=flair1,flair2

REDDIT_KEYWORDS=word1,word2
RSS_KEYWORDS=word3,word4
RSS_FEEDS=https://example.com/feed,https://another.com/rss

DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
CHECK_INTERVAL=300
POST_LIMIT=10

ENABLE_DM=true
DISCORD_TOKEN=your_discord_bot_token_here
DISCORD_USER_IDS=123456789012345678
DISCORD_CHANNEL_IDS=123456789012345678
ADMIN_USER_IDS=123456789012345678

# Optional settings
TIMEZONE=America/Chicago         # default if omitted
WATCH_USERS=someuser,anotherone  # global watched Reddit authors (no "u/")

# v1.7 thread options (optional)
THREAD_MODE=true                # enable thread posting globally
THREAD_TTL_HOURS=24             # cleanup inactive threads after N hours

```

### 4. Enable Discord Bot DMs
1. Create a bot in the **Discord Developer Portal**.
2. Paste its token into `DISCORD_TOKEN`.
3. Enable **Message Content Intent** if needed for your setup and **Use Slash Commands**.
4. Invite it to your server with:
   - Read Messages/View Channels
   - Send Messages
   - Embed Links
   - Use Slash Commands
   - *(Optional)* Read Message History

### 5. Run the Bot with Docker
```yaml
version: "3.8"
services:
  multinotify:
    build: .
    volumes:
      - ./bot.py:/app/bot.py
      - ./.env:/app/.env
      - ./data:/app/data
    restart: unless-stopped
```
Run:
```bash
docker compose up -d --build
docker compose logs -f
```

### 6. Running Multiple Bots
```yaml
version: "3.8"
services:
  multinotify-1:
    build: .
    volumes:
      - ./bot.py:/app/bot.py
      - ./.env.bot1:/app/.env
      - ./data-bot1:/app/data
    restart: unless-stopped

  multinotify-2:
    build: .
    volumes:
      - ./bot.py:/app/bot.py
      - ./.env.bot2:/app/.env
      - ./data-bot2:/app/data
    restart: unless-stopped
```

---

## Notes
## Notes
- Quiet hours and digest times use the bot’s **current timezone**. Default is **America/Chicago**; admins can change it with `/settimezone`.
- If the global subreddit is cleared, global Reddit fetching is disabled until a new subreddit is set; personal subreddits continue to work.
- RSS and Reddit each have **independent** keyword filters.
- Keyword matching is **exact whole word** and case-insensitive.
- `.env` changes made via slash commands persist across restarts when running as a Discord bot.
- Supports Discord webhooks, non-Discord webhooks, channel sends, thread posting, and DMs.
- The bot always loads your `.env` at startup for base configuration.
- **Headless mode:** If no `DISCORD_TOKEN` is set in `.env`, MultiNotify runs webhook-only.
  - Slash commands and all Discord-specific features (channels, threads, DMs) are disabled
  - The following features **work in headless mode without ever running as a bot**:
    - Reddit subreddit monitoring
    - RSS/Atom feed monitoring
    - Global keyword and flair filtering
    - Watched Reddit users (global only, via `.env`)
    - Webhook delivery (Discord and non-Discord)
    - Seen-item tracking and duplicate prevention
    - Persistent configuration loaded from the `data/` directory
- **Thread mode:**
  - When enabled, messages are posted into reusable Discord threads instead of directly into channels.
  - Threads are automatically reused and cleaned up after a configurable TTL.
  - Users may override global thread behavior.
- **Watched users:**
  - Fetches from **global** + **personal** watched lists.
  - Delivered only to users who watch that author (globally or personally).
  - Respect **quiet hours** and **digest**.
  - Per-user **bypass toggles** control subreddit/flair/keyword checks.
  - Global subreddit flairs/keywords **do not** restrict watched-user deliveries.



---

## Updating the Bot
```bash
git pull origin main
docker compose up -d --build
```
Check `.env.example` for new options and add them if needed. For v1.6:
- Optionally add `TIMEZONE` and `WATCH_USERS` to `.env`.
- New personal commands: `/mywatch` and `/mywatchprefs`.
- New admin commands: `/adduserwatch`, `/removeuserwatch`, `/listuserwatches`, `/settimezone`.

---

## Support
For issues, questions, or suggestions, open an issue or ping me:  
[![Discord](https://img.shields.io/badge/Message%20me%20on%20Discord-ethanocurtis-5865F2?logo=discord&logoColor=white)](https://discordapp.com/users/167485961477947392)

You may also [join the official MultiNotify Discord](https://discord.gg/SYCZ8HUTje) for direct support and installation help.

---

## License
MIT
