FROM node:24-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci --ignore-scripts
COPY . .
# prebuild genera public/vendor/sodium.js (libsodium come script separato)
RUN npm run build -- --configuration=production

FROM nginx:1.27-alpine
# nginx sostituisce ${DOMAIN} nel template all'avvio (20-envsubst-on-templates.sh)
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY security-headers.inc.template /etc/nginx/templates/security-headers.inc.template
COPY --from=build /app/dist/safe-web/browser /usr/share/nginx/html
# La configurazione runtime viene montata a /usr/share/nginx/html/config/app-config.json
ENV DOMAIN=localhost
EXPOSE 80
