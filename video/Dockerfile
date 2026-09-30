FROM caddy:2-alpine
COPY video /srv
CMD ["caddy","file-server","--root","/srv","--listen",":8080"]