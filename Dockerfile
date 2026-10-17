# Frontend image. Build context is the repository root or a deliberate private bundle.
FROM node:22-bookworm-slim AS build
WORKDIR /app
COPY services/frontend/package*.json services/frontend/
RUN npm --prefix services/frontend ci --ignore-scripts --no-audit --no-fund
COPY config config
COPY services/frontend services/frontend
RUN npm --prefix services/frontend run build

FROM node:22-bookworm-slim
WORKDIR /app/services/frontend
ENV NODE_ENV=production PORT=3000
COPY --from=build /app/services/frontend/dist ./dist
COPY --from=build /app/services/frontend/server.js /app/services/frontend/private-access.js /app/services/frontend/access-page.js /app/services/frontend/api-proxy.js /app/services/frontend/entrance-assets.js /app/services/frontend/profile-config.mjs /app/services/frontend/package.json ./
COPY --from=build /app/config /app/config
USER node
EXPOSE 3000
CMD ["node", "server.js"]
