FROM caddy:2-alpine
COPY analytics /srv
CMD ["caddy","file-server","--root","/srv","--listen",":8080"]