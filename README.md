# Reddit to Discord Notifier

Monitor a subreddit for new posts (optionally filtered by flair) and automatically send them to a Discord channel via webhook.

## Features

- Monitor any subreddit
- Filter by one or multiple flairs (comma-separated)
- Option to post all new posts (no flair filter)
- Sends to Discord using a webhook
- Runs easily via Docker (Linux, Raspberry Pi, or Windows)

---

## How to Use (Linux / Raspberry Pi)

### 1. Clone this repository

```bash
git clone https://github.com/ethanocurtis/discord-reddit-bot.git
cd discord-reddit-bot
```

---

### 2. Create a Reddit App (for API keys)

1. Log in to https://www.reddit.com/prefs/apps
2. Scroll to "Developed Applications" and click "create app".
3. Fill in:
   - Name: `discord-notifier`
   - App type: `script`
   - Redirect URI: `http://localhost`
4. After creating, copy your:
   - client_id (under the app name)
   - client_secret (next to "secret")

---

### 3. Set up your `.env` file

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
```

- `SUBREDDIT`: The subreddit (no `r/`).
- `ALLOWED_FLAIR`: Comma-separated flairs. Leave blank for all posts.
- `DISCORD_WEBHOOK_URL`: Create one in Discord (Server Settings â†’ Integrations â†’ Webhooks).
- `DEBUG`: Set to `true` to send the last 10 posts immediately (ignoring duplicates), then exit (for testing).

---

### 4. Use `.env.example` for easy setup

The repo includes a `.env.example`. Copy it and rename:
```bash
cp .env.example .env
```
Then edit with your keys.

---

### 5. Run the bot with Docker

Build and start:
```bash
docker compose up -d --build
```

Watch logs:
```bash
docker compose logs -f
```

The bot will post the latest 10 matching posts at startup, then check every `CHECK_INTERVAL` (default 5 minutes) for new ones.

---

### 6. Running Multiple Bots (Optional)

Want to monitor different subreddits or flairs? Duplicate the service in `docker-compose.yml`:

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

Each instance can use a different `.env`.

---

## Using on Windows (Experimental)

While designed for Linux/Pi, you can run this on Windows if you:
1. Install Docker Desktop (https://www.docker.com/products/docker-desktop/).
2. Clone the repository (use GitHub Desktop or `git clone`).
3. Create the `.env` as above.
4. Open PowerShell or Command Prompt in the project folder and run:
   ```powershell
   docker compose up -d --build
   ```
Logs can be viewed with:
```powershell
docker compose logs -f
```

Note: Windows testing is limited. Most users should run on a server or Raspberry Pi for reliability.

---

## Notes

- `.env` is ignored by Git (your secrets will not be uploaded).
- Supports any subreddit and any flair (or all posts).
- Debug mode is helpful for testing.

---

## License

MIT