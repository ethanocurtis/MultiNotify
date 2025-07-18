# Reddit to Discord Notifier

Monitor a subreddit for new posts (optionally filtered by flair) and automatically send them to a Discord channel via webhook, with optional DM notifications.

## Table of Contents
- [Features](#features)
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
- Monitor any subreddit
- Filter by one or multiple flairs (comma-separated)
- Send posts to Discord via webhook (Discord embeds or plain text for other platforms)
- Optional DM notifications to one or more Discord users
- Simple setup with Docker

## How to Use

### 1. Clone the Repository
```bash
git clone https://github.com/ethanocurtis/discord-reddit-bot.git
cd discord-reddit-bot
```

### 2. Create a Reddit App
1. Log in to [https://www.reddit.com/prefs/apps](https://www.reddit.com/prefs/apps)
2. Scroll to **"Developed Applications"** and click **"create app"**.
3. Fill in:
   - **Name**: `discord-notifier`
   - **App type**: `script`
   - **Redirect URI**: `http://localhost`
4. Copy your `client_id` (under the app name) and `client_secret` (next to "secret").

### 3. Set Up Your .env File
Create a `.env` file in the project folder with:
```env
REDDIT_CLIENT_ID=your_client_id_here
REDDIT_CLIENT_SECRET=your_client_secret_here
REDDIT_USER_AGENT=discord-notifier-bot by u/yourusername
SUBREDDIT=selfhosted
ALLOWED_FLAIR=Release,Product Announcement
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/your_webhook_here
CHECK_INTERVAL=300
POST_LIMIT=10
DEBUG=false
ENABLE_DM=false
DISCORD_BOT_TOKEN=your_discord_bot_token_here
DISCORD_USER_IDS=123456789012345678,987654321098765432
```

Descriptions of each variable:
- `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET`: Credentials for Reddit API (from your Reddit app).
- `REDDIT_USER_AGENT`: A descriptive name for the bot, required by Reddit.
- `SUBREDDIT`: The subreddit to monitor (no `r/`).
- `ALLOWED_FLAIR`: Comma-separated list of flairs to filter. Leave blank to send all posts.
- `DISCORD_WEBHOOK_URL`: The webhook where posts will be sent (Discord, Mattermost, Slack, etc.).
- `CHECK_INTERVAL`: How often (in seconds) to check for new Reddit posts.
- `POST_LIMIT`: Number of recent posts to fetch each cycle (and at startup).
- `DEBUG`: Set to `true` to send the last 10 posts once, then exit (for testing).
- `ENABLE_DM`: Set to `true` to also send direct messages via the Discord bot.
- `DISCORD_BOT_TOKEN`: The token for your Discord bot (required if DM is enabled).
- `DISCORD_USER_IDS`: Comma-separated numeric Discord user IDs to receive DMs.

### 4. Enable Discord Bot DMs
1. Go to [Discord Developer Portal](https://discord.com/developers/applications).
2. Click **"New Application"**, name it (e.g., `Reddit Notifier`), and click **Create**.
3. In the left sidebar, go to **"Bot"** → **"Add Bot"**.
4. Copy the **Bot Token** and paste it into `DISCORD_BOT_TOKEN` in `.env`.
5. Enable **"Direct Messages Intent"** in the bot settings.
6. Under **OAuth2 → URL Generator**, select `bot` and grant:
   - `Send Messages`
   - `Read Messages/View Channels`
7. Copy the generated URL, invite the bot to your server, and get the **User IDs** of people to DM (enable Developer Mode in Discord, right-click user → "Copy User ID").

### 5. Run the Bot with Docker
```bash
docker compose up -d --build
docker compose logs -f
```
The bot will post the latest 10 posts at startup, then check every `CHECK_INTERVAL` seconds.

### 6. Running Multiple Bots
For different subreddits/flairs, duplicate the service in `docker-compose.yml`:
```yaml
version: "3.8"
services:
  reddit-notifier-1:
    build: .
    env_file:
      - .env
    restart: unless-stopped
  reddit-notifier-2:
    build: .
    env_file:
      - .env.another
    restart: unless-stopped
```

## Notes
- Works with Discord, Mattermost, Slack (webhooks).
- Debug mode (`DEBUG=true`) sends the last 10 posts immediately, then exits.

## License
MIT
