FROM node:22-alpine AS build
WORKDIR /application
COPY apps/admin-console/package.json apps/admin-console/tsconfig.json apps/admin-console/vite.config.ts ./
COPY apps/admin-console/index.html ./
COPY apps/admin-console/src ./src
RUN npm install && npm run build

FROM nginx:1.27-alpine
COPY apps/admin-console/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /application/dist /usr/share/nginx/html
EXPOSE 80
