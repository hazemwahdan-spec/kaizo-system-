FROM caddy:2-alpine
COPY . /srv
EXPOSE 8080
CMD ["caddy","file-server","--root","/srv","--listen",":8080"]
