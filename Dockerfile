# Works on x86-64 and on the ARM (Ampere) VMs of Oracle Cloud.
FROM node:24-bookworm-slim

# ffmpeg: video frames for transcripts. python3/make/g++: only used if better-sqlite3 has no prebuilt binary for the CPU.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg python3 make g++ ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev

COPY src ./src
COPY scripts ./scripts

ENV NODE_ENV=production
# bot.db and the fix archive live here: mount a volume so they survive updates
VOLUME ["/app/data"]

CMD ["node", "src/index.js"]
