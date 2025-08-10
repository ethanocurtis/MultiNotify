FROM python:3.11-slim

WORKDIR /app

COPY bot.py .

# Install dependencies for Reddit, webhooks, Discord, and async performance
RUN pip install --no-cache-dir praw requests discord.py uvloop feedparser

# Force unbuffered output so logs show up instantly in `docker logs`
ENV PYTHONUNBUFFERED=1

# Use uvloop as the default asyncio loop for better performance
ENV UVLOOP=1

CMD ["python", "bot.py"]
