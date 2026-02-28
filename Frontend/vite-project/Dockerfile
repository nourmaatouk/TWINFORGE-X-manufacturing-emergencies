FROM node:22-alpine AS builder
WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

ARG VITE_API_URL=/api
ARG VITE_DASHBOARD_URL=http://localhost:8001
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_DASHBOARD_URL=$VITE_DASHBOARD_URL

RUN npm run build

FROM nginx:1.27-alpine
ARG NGINX_CONF=default.conf
ENV AUTH_BACKEND_HOST=auth-backend \
    DASHBOARD_HOST=twinforge-dashboard
COPY nginx/${NGINX_CONF} /etc/nginx/templates/default.conf.template
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
