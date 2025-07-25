
# MultiNotify(v1.3)

![Python](https://img.shields.io/badge/Python-3.8+-blue) ![Discord](https://img.shields.io/badge/Discord-Bot-brightgreen) ![Webhooks](https://img.shields.io/badge/Webhook-Supported-green) ![Mattermost](https://img.shields.io/badge/Mattermost-Compatible-orange) ![Slack](https://img.shields.io/badge/Slack-Compatible-lightgrey) ![DM Mode](https://img.shields.io/badge/DM-Mode%20Supported-purple) ![License: MIT](https://img.shields.io/badge/License-MIT-yellow)

Monitor a subreddit for new posts (optionally filtered by flair) and automatically send them to Discord, Mattermost, Slack, or other services via webhook. Supports **Discord embeds, DM notifications, slash commands, automatic `.env` updates**, and is fully containerized for easy deployment.

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
- [License](#license)

## Features
- Monitor any subreddit for new posts.
- Filter by one or multiple flairs (or watch all posts).
- Send posts via **Discord embeds** (with subreddit, flair, author) or plain text for Slack/others.
- Optional **DM notifications** to one or more Discord users (with flair info).
- Change settings live with **slash commands** (no restart needed).
- Automatically updates `.env` so settings persist.
- **Always loads your saved `.env` at startup** (no `/reloadenv` needed unless manually editing).
- Supports **Discord-specific embeds** and plain text fallback for others.

## Slash Commands

All commands require the user to be listed in `ADMIN_USER_IDS` in `.env`.  
Bot replies use **Discord embeds** for clean, consistent output.

### Configuration
- `/setsubreddit <name>` — Set the subreddit being monitored.
- `/setinterval <seconds>` — Set how often the bot checks Reddit.
- `/setpostlimit <number>` — Set how many posts to fetch each cycle.
- `/setwebhook [url]` — Set or clear the webhook (blank clears it).  
  Discord webhooks get full embeds; others get plain text.
- `/setflairs [flair1, flair2,...]` — Set which flairs to monitor.  
  Run with **no arguments** to clear and watch all posts.
- `/enabledms <true/false>` — Enable or disable DM notifications.

### DM User Management
- `/adddmuser <user_id>` — Add a user to the DM list.
- `/removedmuser <user_id>` — Remove a user from the DM list.

### Info & Maintenance
- `/status` — Show current settings (subreddit, interval, flairs, post limit, DM status, DM users, and webhook).  
  Webhook and sensitive data are shown only to you (ephemeral).
- `/help` — Show this command list in Discord.
- `/reloadenv` — Reload `.env` without restarting (useful if you edited it manually while the bot is running).
- `/whereenv` — Show the path to the `.env` file being used.

## Webhook Behavior
- **Discord webhooks** use embeds with:
  - Subreddit name
  - Flair (or "No Flair")
  - Post author
  - Post title (linked)
  - Reddit branding icon
- **Non-Discord webhooks (Slack, Mattermost, etc.)** use plain text for compatibility.
- **DM notifications** include flair, author, title, and a link.

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
Include your credentials:
```env
REDDIT_CLIENT_ID=your_client_id_here
REDDIT_CLIENT_SECRET=your_client_secret_here
REDDIT_USER_AGENT=multinotify-bot by u/yourusername
SUBREDDIT=asubreddit
ALLOWED_FLAIR=flairs,go,here
DISCORD_WEBHOOK_URL=
CHECK_INTERVAL=300
POST_LIMIT=10
ENABLE_DM=true
DISCORD_TOKEN=your_discord_bot_token_here
DISCORD_USER_IDS=123456789012345678
ADMIN_USER_IDS=123456789012345678
```

### 4. Enable Discord Bot DMs
1. Create a bot in the [Discord Developer Portal](https://discord.com/developers/applications).
2. Copy its token into `DISCORD_TOKEN`.
3. Enable **"Direct Messages Intent"**.
4. Invite it to your server with necessary permissions(see below).

### Required Discord Permissions

When inviting the bot to your server, make sure it has the following **minimum permissions**:

- **Read Messages/View Channels** – So the bot can see the channels where you run commands.
- **Send Messages** – Allows the bot to reply to your slash commands.
- **Embed Links** – Required to send rich embeds (for slash command responses and Discord webhooks).
- **Use Slash Commands** – Automatically included for bots but must be enabled on your application.
- **Read Message History** *(optional)* – Only needed if you want the bot to reference past messages (not required by default).

You do **not** need to give the bot Administrator rights. These permissions are enough for all its features.

### 5. Run the Bot with Docker
Use `docker-compose.yml` to build and run the bot. Mount `.env` so settings persist.

```yaml
version: "3.8"

services:
  reddit-notifier:
    build: .
    volumes:
      - ./bot.py:/app/bot.py
      - ./.env:/app/.env
    restart: unless-stopped
```

```bash
docker compose up -d --build
docker compose logs -f
```

### 6. Running Multiple Bots
Duplicate the service in `docker-compose.yml` (each with its own `.env`):
```yaml
version: "3.8"
services:
  reddit-notifier-1:
    build: .
    volumes:
      - ./bot.py:/app/bot.py
      - ./.env:/app/.env
    restart: unless-stopped

  reddit-notifier-2:
    build: .
    volumes:
      - ./bot.py:/app/bot.py
      - ./.env.another:/app/.env
    restart: unless-stopped
```

## Notes
- The bot **always loads your `.env` at startup**.
- `.env` changes made via commands persist across restarts.
- Automatically detects Discord vs other webhooks (embeds vs plain text).
- The wiki is currently out of date and will be updated ASAP.

## License
MIT

## Support

For issues, questions, or suggestions, feel free to open an issue on GitHub or contact me:  
[![Discord](https://img.shields.io/badge/Message%20me%20on%20Discord-ethanocurtis-5865F2?logo=discord&logoColor=white)](https://discordapp.com/users/167485961477947392)