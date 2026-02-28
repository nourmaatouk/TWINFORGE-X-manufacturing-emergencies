FROM node:22-alpine

WORKDIR /app

ENV NODE_ENV=production

COPY package*.json ./
RUN npm ci --omit=dev

COPY . .

# Create /data/ for SQLite DB (AUTH_DB_PATH=/data/auth.db)
RUN mkdir -p /data

EXPOSE 5000

CMD ["node", "server.js"]
