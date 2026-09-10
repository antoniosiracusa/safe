FROM node:24-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build -- --configuration=production

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist/safe-web/browser /usr/share/nginx/html
# La configurazione runtime viene montata a /usr/share/nginx/html/config/app-config.json
EXPOSE 80
