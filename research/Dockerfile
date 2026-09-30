FROM caddy:2-alpine
COPY research /srv
CMD ["caddy","file-server","--root","/srv","--listen",":8080"]