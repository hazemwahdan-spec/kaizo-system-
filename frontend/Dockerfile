FROM caddy:2-alpine
COPY . /srv
CMD ["caddy","file-server","--root","/srv","--listen",":8080"]
