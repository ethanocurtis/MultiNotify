# MultiNotify

![Python](https://img.shields.io/badge/Python-3.8+-blue) ![Discord](https://img.shields.io/badge/Discord-Bot-brightgreen) ![Webhooks](https://img.shields.io/badge/Webhook-Supported-green) ![Mattermost](https://img.shields.io/badge/Mattermost-Compatible-orange) ![Slack](https://img.shields.io/badge/Slack-Compatible-lightgrey) ![DM Mode](https://img.shields.io/badge/DM-Mode%20Supported-purple) ![License: MIT](https://img.shields.io/badge/License-MIT-yellow)

Monitor a subreddit for new posts (optionally filtered by flair) and automatically send them to Discord, Mattermost, Slack, or other services via webhook. Supports **Discord embeds, DM notifications, dynamic commands, automatic `.env` updates**, and is fully containerized for easy deployment.

## Table of Contents
- [Features](#features)
- [Commands](#commands)
- [How to Use](#how-to-use)
  - [Clone the Repository](#1-clone-the-repository)
  - [Create a Reddit App](#2-create-a-reddit-app)
  - [Set Up the .env File](#3-set-up-your-env-file)
  - [Enable Discord Bot DMs](#4-enable-discord-bot-dms)
  - [Run the Bot](#5-run-the-bot-with-docker)
  - [Multiple Bots](#6-running-multiple-bots)
- [First Run Tips](#first-run-tips)
- [Notes](#notes)
- [License](#license)

## Features
- Monitor any subreddit for new posts.
- Filter by one or multiple flairs (or watch all posts).
- Send posts via Discord embeds (or plain text for Slack/others).
- Optional DM notifications to one or more Discord users.
- Change settings live with bot commands (no restart needed).
- Automatically updates `.env` so settings persist.
- Shows last Reddit check time in `!status`.
- Includes a built-in `!help` command listing all available commands.
- Simple out-of-the-box deployment with Docker.

## Commands

All commands require the user to be listed in `ADMIN_USER_IDS` in `.env`.  
Bot replies use **Discord embeds** for clean, consistent output.

### Configuration
- `!setsubreddit [name]` — Set or view the subreddit being monitored.
- `!setinterval [seconds]` — Set or view how often the bot checks Reddit.
- `!setpostlimit [number]` — Set or view how many posts to fetch each cycle.
- `!setflairs [flair1, flair2,...]` — Set which flairs to monitor.  
  Run with **no arguments** to clear and watch all posts.
- `!enabledms [true/false]` — Enable, disable, or show the current DM status.

### DM User Management
- `!adddmuser [user_id]` — Add a user to the DM list, or show the current list.
- `!removedmuser [user_id]` — Remove a user from the DM list, or show the current list.

### Info & Maintenance
- `!status` — Show current settings (subreddit, interval, flairs, DM status, post limit, and last Reddit check time).
- `!help` — Show this command list in Discord.
- `!reloadenv` — Reload `.env` without restarting.
- `!whereenv` — Show the path to the `.env` file being used.

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
4. Copy the `client_id` (under the app name) and `client_secret` (next to "secret").

### 3. Set Up Your .env File
An example `.env.example` file is included. Copy and configure it:
```bash
cp .env.example .env
```

Edit `.env` to include your credentials:
```env
REDDIT_CLIENT_ID=your_client_id_here
REDDIT_CLIENT_SECRET=your_client_secret_here
REDDIT_USER_AGENT=multinotify-bot by u/yourusername
SUBREDDIT=asubreddit
ALLOWED_FLAIR=
DISCORD_WEBHOOK_URL=
CHECK_INTERVAL=300
POST_LIMIT=10
DEBUG=false
ENABLE_DM=true
DISCORD_BOT_TOKEN=your_discord_bot_token_here
DISCORD_USER_IDS=123456789012345678
ADMIN_USER_IDS=123456789012345678
```

### 4. Enable Discord Bot DMs
1. Go to [Discord Developer Portal](https://discord.com/developers/applications).
2. Create a new application and add a bot.
3. Copy the bot token into `DISCORD_BOT_TOKEN` in `.env`.
4. Enable **"Direct Messages Intent"** for the bot.
5. Invite it to your server with `Send Messages` and `Read Messages/View Channels` permissions.
6. Get Discord user IDs (right-click user → "Copy User ID") and add them to `DISCORD_USER_IDS`.

### 5. Run the Bot with Docker

Below is a sample `docker-compose.yml` you can use to run MultiNotify quickly:

```yaml
version: "3.8"

services:
  reddit-notifier:
    build: .
    volumes:
      - ./bot.py:/app/bot.py        # Sync your bot code
      - ./.env:/app/.env            # Mount .env as a file (not a directory!)
    env_file:
      - .env                        # Load environment variables
    restart: unless-stopped

```

```bash
docker compose up -d --build
docker compose logs -f
```

The bot will:
- Post the last 10 posts at startup.
- Check Reddit every `CHECK_INTERVAL` seconds.
- Send posts to Discord as embeds (or plain text for Slack).
- Send DMs to specified users (if enabled).

### 6. Running Multiple Bots
To run for multiple subreddits/flairs, duplicate the service in `docker-compose.yml`:
```yaml
version: "3.8"
services:
  reddit-notifier-1:
    build: .
    volumes:
      - ./bot.py:/app/bot.py
      - ./.env:/app/.env
    env_file:
      - .env
    restart: unless-stopped
  reddit-notifier-2:
    build: .
    volumes:
      - ./bot.py:/app/bot.py
      - ./.env.another:/app/.env
    env_file:
      - .env.another
    restart: unless-stopped
```

## First Run Tips
Once the bot is running:
1. Use `!help` to see all available commands.
2. Run `!setsubreddit <subreddit>` to choose which subreddit to monitor.
3. Use `!setflairs` (with no arguments) to accept all posts, or specify flairs.
4. Check everything with `!status`.

## Webhook-Only Mode
You can run MultiNotify **without a Discord bot** by setting:
```
ENABLE_DM=false
DISCORD_BOT_TOKEN=
```
As long as you provide a valid `DISCORD_WEBHOOK_URL`, the bot will post to Discord, Slack, or other webhooks without logging in as a Discord bot.

## Notes
- Automatically detects if your webhook is Discord, Slack, or another service:
  - **Discord** gets embedded messages.
  - **Slack/others** get plain text for compatibility.
- `.env` changes made with commands are saved and persist after restarts.
- Debug mode (`DEBUG=true`) fetches 10 posts then exits (for testing).
- Can run as **DM-only** by leaving `DISCORD_WEBHOOK_URL` blank.

## License
MIT
