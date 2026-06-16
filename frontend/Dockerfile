FROM registry.example.com/dockerhub/library/nginx:1.27-alpine

# Config nginx personnalisée
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copier les fichiers statiques du frontend
COPY . /usr/share/nginx/html

EXPOSE 80
