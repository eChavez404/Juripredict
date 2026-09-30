# Estágio de Build
FROM node:24-alpine AS build

WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Estágio de Produção (Nginx)
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html

# Configuração simples do Nginx para React Router
RUN echo 'server { listen 80; location / { root /usr/share/nginx/html; index index.html; try_files $uri $uri/ /index.html; } }' > /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
