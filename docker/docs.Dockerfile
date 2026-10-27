# Build the HTML first; the build context is docs/_build/html only.
FROM nginx:1.30.6-alpine

ARG API_VERSION
ARG DOCS_REVISION
LABEL org.opencontainers.image.title="Station Data API documentation" \
      org.opencontainers.image.version="${API_VERSION}" \
      org.opencontainers.image.revision="${DOCS_REVISION}" \
      org.opencontainers.image.source="https://github.com/pacificclimate/pdp-station-api"

RUN apk upgrade --no-cache

COPY . /usr/share/nginx/html/
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
