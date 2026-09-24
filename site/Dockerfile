# tracebi.com — the marketing site and the static docs, as one small image.
#
# Copies only what is public: the landing page, its assets, the sample report,
# and the generated docs site. build_docs.py and README.md stay out of the
# image, because a static host serves every file it is given.
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html /usr/share/nginx/html/index.html
COPY assets /usr/share/nginx/html/assets
COPY sample /usr/share/nginx/html/sample
COPY docs /usr/share/nginx/html/docs
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1
