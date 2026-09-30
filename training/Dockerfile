FROM caddy:2-alpine
COPY training /srv
CMD ["caddy","file-server","--root","/srv","--listen",":8080"]