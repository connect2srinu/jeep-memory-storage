FROM node:22-alpine AS build
WORKDIR /application
ARG VITE_MEMORY_API_URL=/memory-api/api/v1/admin
ENV VITE_MEMORY_API_URL=$VITE_MEMORY_API_URL
COPY apps/admin-console/package.json apps/admin-console/tsconfig.json apps/admin-console/vite.config.ts ./
COPY apps/admin-console/index.html ./
COPY apps/admin-console/src ./src
RUN npm ci && npm run build

FROM nginx:1.27-alpine
COPY apps/admin-console/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /application/dist /usr/share/nginx/html
EXPOSE 80
