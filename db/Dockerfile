# PostGIS base image + pgvector: the single database of ADR-004 needs both
# extensions, and no stock image ships the pair.
FROM postgis/postgis:16-3.4

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-16-pgvector \
    && rm -rf /var/lib/apt/lists/*
