# ---- deps ----
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci || npm install

# ---- build ----
FROM node:22-alpine AS build
WORKDIR /app
ARG API_PROXY_TARGET=http://app:8000
ENV API_PROXY_TARGET=$API_PROXY_TARGET
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

# ---- run ----
FROM node:22-alpine AS run
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3210
ARG API_PROXY_TARGET=http://app:8000
ENV API_PROXY_TARGET=$API_PROXY_TARGET
COPY --from=build /app/.next ./.next
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/package.json ./package.json
COPY --from=build /app/next.config.mjs ./next.config.mjs
COPY --from=build /app/public ./public
EXPOSE 3210
CMD ["npm", "run", "start"]
