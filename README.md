# MultiNotify (v1.4)

![Python](https://img.shields.io/badge/Python-3.8+-blue) ![Discord](https://img.shields.io/badge/Discord-Bot-brightgreen) ![Webhooks](https://img.shields.io/badge/Webhook-Supported-green) ![Mattermost](https://img.shields.io/badge/Mattermost-Compatible-orange) ![Slack](https://img.shields.io/badge/Slack-Compatible-lightgrey) ![DM Mode](https://img.shields.io/badge/DM-Mode%20Supported-purple) ![License: MIT](https://img.shields.io/badge/License-MIT-yellow)

Monitor subreddits **and** RSS/Atom feeds for new content (optionally filtered by flair or separate keyword lists) and automatically send them to Discord, Mattermost, Slack, or other services via webhook or directly to specific Discord channels. Supports **Discord embeds, DM notifications, slash commands, automatic `.env` updates**, and is fully containerized for easy deployment.

## Table of Contents
- [Features](#features)
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
- [License](#license)

## Features

## Global vs Personal Settings

**Global settings** are managed by admins listed in `ADMIN_USER_IDS` in `.env` and apply to all users by default.  
They include global subreddit, flairs, keywords, RSS feeds, webhooks, quiet hours, etc.

**Personal settings** can be set by any user and override the global settings for that user's notifications.  
A user can have their own subreddit(s), flairs, keywords, RSS feeds, digest mode, and quiet hours.

**Priority:** Personal settings override global settings for the same category.  
For example, if a personal subreddit is set, the user will only receive notifications for that subreddit (plus their own feeds), ignoring the global subreddit.

If the global subreddit is cleared, global Reddit monitoring is paused until one is set again. Personal subreddits still work.


- Monitor any subreddit for new posts.
- Monitor any number of RSS or Atom feeds.
- Separate **keyword filtering** for Reddit and RSS (whole word matching, case-insensitive).
- Filter Reddit posts by one or multiple flairs (or watch all posts).
- Send notifications:
  - **Discord embeds** (subreddit/feed, flair/source, author, link).
  - Plain text for Slack, Mattermost, etc.
  - Directly into specific Discord channels (via bot, no webhook required).
  - Optional **DM notifications** to one or more Discord users.
- Change settings live with **slash commands** (no restart needed).
- Automatically updates `.env` so settings persist.
- Always loads your saved `.env` at startup.
- Supports **Discord-specific embeds** and plain text fallback for others.

> ⚙️ All modules (webhooks, channel sends, flair filtering, keyword filtering, DMs) can be enabled or disabled independently.

---

## Slash Commands

All commands require the user to be listed in `ADMIN_USER_IDS` in `.env`.  
Bot replies use **Discord embeds** for clean, consistent output.

### Reddit Configuration
- `/setsubreddit [name]` — Set the subreddit being monitored. Run with **no arguments** to clear and stop monitoring any subreddit.
- `/setinterval <seconds>` — Set how often the bot checks for new items (affects both Reddit and RSS).
- `/setpostlimit <number>` — Set how many Reddit posts to fetch each cycle.
- `/setflairs [flair1, flair2,...]` — Set which flairs to monitor (**case sensitive**).  
  Run with **no arguments** to clear the flair filter and watch all posts.
- `/setredditkeywords [keyword1, keyword2,...]` — Set keywords for Reddit filtering.  
  Run with **no arguments** to disable keyword filtering and allow all Reddit posts.

### RSS Configuration
- `/addrss <url>` — Add an RSS or Atom feed URL.
- `/removerss <url>` — Remove a feed.
- `/listrss` — List all configured feeds.
- `/setrsskeywords [keyword1, keyword2,...]` — Set keywords for RSS filtering.  
  Run with **no arguments** to disable keyword filtering and allow all RSS items.

### Combined Keyword Control
- `/setkeywords [keyword1, keyword2,...]` — **Legacy**: set the same keyword list for both Reddit and RSS at once.

### Notification Settings
- `/setwebhook [url]` — Set or clear the webhook (blank clears it).  
  Discord webhooks get embeds; others get plain text.
- `/enabledms <true/false>` — Enable or disable DM notifications.
- `/adddmuser <user_id>` — Add a user to the DM list.
- `/removedmuser <user_id>` — Remove a user from the DM list.
- `/setquiethours <start_hour> <end_hour>` — Set quiet hours in **UTC** (suppress notifications during these hours).
- `/setdigest <off|daily|weekly> [HH:MM] [day(mon..sun)]` — Set personal digest mode and optional send time/day.



### Personal Settings Commands
These commands are available to all users and control **only your own notifications**. They override global settings for that category.

#### Personal Reddit
- `/mysubreddit [name]` — Set your personal subreddit. Blank clears.
- `/myflairs [flair1, flair2,...]` — Set your personal flairs. Blank clears.
- `/myredditkeywords [kw1, kw2,...]` — Set personal Reddit keywords. Blank clears.

#### Personal RSS
- `/myrssadd <url>` — Add a personal RSS/Atom feed.
- `/myrssremove <url>` — Remove a personal RSS feed.
- `/myrsslist` — List your personal RSS feeds.
- `/myrsskeywords [kw1, kw2,...]` — Set personal RSS keywords. Blank clears.

#### Personal Delivery
- `/mypreferredchannel <channel_id>` — Set preferred Discord channel for personal notifications. Blank clears (use DM).
- `/setdigest <off|daily|weekly> [HH:MM] [day]` — Set personal digest mode.
- `/setquiethours <start_hour> <end_hour>` — Set personal quiet hours (UTC).


### Discord Channel Notifications
- `/addchannel <channel_id>` — Add a Discord channel ID for notifications.
- `/removechannel <channel_id>` — Remove a channel ID.
- `/listchannels` — Show all channels set for notifications.

### Info & Maintenance
- `/status` — Show current settings (subreddit, interval, flairs, Reddit keywords, RSS keywords, post limit, DM status, DM users, webhook, channels, and RSS feeds).  
  Webhook and sensitive data are shown only to you (ephemeral).
- `/help` — Show this command list in Discord.
- `/reloadenv` — Reload `.env` without restarting (useful if you edited it manually).
- `/whereenv` — Show the path to the `.env` file being used.

---

## Webhook Behavior

- **Discord webhooks** use rich embeds with:
  - Source (Subreddit or Feed name)
  - Flair (Reddit) or Feed domain (RSS)
  - Author (Reddit only)
  - Title (linked to source)
  - Icon branding
- **Non-Discord webhooks** (Slack, Mattermost, etc.) use plain text for compatibility.
- **DM notifications** include source, flair/feed name, author (if Reddit), title, and a link.
- **Channel sends** use embeds similar to Discord webhooks but are sent directly by the bot.

---

## How to Use

### 1. Clone the Repository
```bash
git clone https://github.com/ethanocurtis/MultiNotify.git
cd MultiNotify
```

### 2. Create a Reddit App
1. Log in to [https://www.reddit.com/prefs/apps](https://www.reddit.com/prefs/apps).
2. Under **"Developed Applications"**, click **"create app"**.
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
Example configuration:
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
```

### 4. Enable Discord Bot DMs
1. Create a bot in the [Discord Developer Portal](https://discord.com/developers/applications).
2. Copy its token into `DISCORD_TOKEN`.
3. Enable **"Direct Messages Intent"**.
4. Invite it to your server with the required permissions.

**Minimum Permissions**:
- Read Messages/View Channels
- Send Messages
- Embed Links
- Use Slash Commands
- *(Optional)* Read Message History

### 5. Run the Bot with Docker
```yaml
version: "3.8"

services:
  reddit-notifier:
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
  reddit-notifier-1:
    build: .
    volumes:
      - ./bot.py:/app/bot.py
      - ./.env.bot1:/app/.env
      - ./data-bot1:/app/data
    restart: unless-stopped

  reddit-notifier-2:
    build: .
    volumes:
      - ./bot.py:/app/bot.py
      - ./.env.bot2:/app/.env
      - ./data-bot2:/app/data
    restart: unless-stopped
```


---

## Notes
- If the subreddit is cleared, global Reddit fetching is disabled until a new subreddit is set.
- Quiet hours use **UTC** time.
- RSS and Reddit each have **independent keyword filters**.
- Keyword matching is **exact whole word** and case-insensitive.
- `.env` changes made via commands persist across restarts.
- Supports Discord webhooks, non-Discord webhooks, channel sends, and DMs.
- The bot always loads your `.env` at startup.

---

## Updating the Bot

To update to the latest version:
```bash
git pull origin main
docker compose up -d --build
```
Check `.env.example` for new options and add them if needed.  

---

## Support

For issues, questions, or suggestions, feel free to open an issue on GitHub or contact me:  
[![Discord](https://img.shields.io/badge/Message%20me%20on%20Discord-ethanocurtis-5865F2?logo=discord&logoColor=white)](https://discordapp.com/users/167485961477947392)

---

## License
MIT