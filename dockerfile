FROM python:3.11-slim

WORKDIR /app

COPY bot.py .

RUN pip install praw requests

CMD ["python", "bot.py"]
