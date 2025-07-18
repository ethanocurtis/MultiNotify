# Reddit to Discord Notifier

Monitor a subreddit for new posts with a specific flair and automatically send them to a Discord channel via webhook.

## ✅ Features

- Monitor any subreddit
- Filter by specific flair (e.g. "Product Announcement")
- Send matching posts to Discord using a webhook
- Simple setup with Docker

---

## 🚀 How to Use

### 1. Clone this repository

```bash
git clone https://github.com/ethanocurtis/discord-reddit-bot.git
cd discord-reddit-bot
```

---

### 2. Create a Reddit App (to get API keys)

1. Log in to [https://www.reddit.com/prefs/apps](https://www.reddit.com/prefs/apps)
2. Scroll to **"Developed Applications"** and click **"create app"**.
3. Fill in:
   - **Name**: `discord-notifier`
   - **App type**: `script`
   - **Redirect URI**: `http://localhost`
4. After creating, copy your:
   - `client_id` (under the app name)
   - `client_secret` (next to "secret")

---

### 3. Set up your `.env` file

Create a `.env` file in the project folder with these contents:

```env
REDDIT_CLIENT_ID=your_client_id_here
REDDIT_CLIENT_SECRET=your_client_secret_here
REDDIT_USER_AGENT=discord-notifier-bot
SUBREDDIT=selfhosted
ALLOWED_FLAIR=Product Announcement
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/your_webhook_here
CHECK_INTERVAL=300
POST_LIMIT=10
```

- `SUBREDDIT`: The subreddit to monitor (without `r/`).
- `ALLOWED_FLAIR`: Only posts with this flair will be sent. Leave blank to send **all new posts**.
- `DISCORD_WEBHOOK_URL`: Create a webhook in your Discord server (Server Settings → Integrations → Webhooks).

---

### 4. Use `.env.example` for easy setup

This repository includes an example file (`.env.example`).  
Copy it and rename it to `.env` to get started:

```bash
cp .env.example .env
```

Then edit it with your own values.

---

### 5. Run the bot with Docker

Build and start the container:
```bash
docker compose up -d --build
```

Check logs to confirm it’s running:
```bash
docker compose logs -f
```

The bot will now check the subreddit every 5 minutes (or whatever `CHECK_INTERVAL` is set to) and post matching new posts to Discord.

---

### 6. Running multiple bots (optional)

Want to monitor **different subreddits or multiple flairs**?  
You can duplicate the service in `docker-compose.yml` like this:

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

Each one can have its own `.env` file for separate subreddits/flairs.

---

## 📄 Notes

- The `.env` file is ignored by Git (for security) — don’t commit your secrets.
- You can run this on any server or Raspberry Pi using Docker.
- Supports any subreddit and any flair.

---

## 📜 License

MIT
