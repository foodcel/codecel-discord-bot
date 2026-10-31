# Works on x86-64 and on the ARM (Ampere) VMs of Oracle Cloud.
FROM python:3.12-slim-bookworm

# ffmpeg: video frames for transcripts.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY bot ./bot
COPY scripts ./scripts

ENV PYTHONUNBUFFERED=1
# bot.db and the fix archive live here: mount a volume so they survive updates
VOLUME ["/app/data"]

CMD ["python", "-m", "bot"]
