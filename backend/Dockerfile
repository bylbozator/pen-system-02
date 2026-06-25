FROM python:3.11-slim-bookworm AS builder

WORKDIR /app

# Замена репозиториев на зеркало Яндекса (опционально, игнорируем ошибку если файла нет)
RUN sed -i 's/deb.debian.org/mirror.yandex.ru/g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || true && \
    sed -i 's|security.debian.org|mirror.yandex.ru|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || true

RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev curl libmagic1 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --user -r requirements.txt

FROM python:3.11-slim-bookworm

WORKDIR /app

RUN sed -i 's/deb.debian.org/mirror.yandex.ru/g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || true && \
    sed -i 's|security.debian.org|mirror.yandex.ru|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || true

RUN apt-get update && apt-get install -y curl libmagic1 && rm -rf /var/lib/apt/lists/*

COPY --from=builder /root/.local /root/.local

COPY ./app /app/app
COPY ./alembic.ini /app/
COPY ./migrations /app/migrations

ENV PATH=/root/.local/bin:$PATH

CMD ["sh", "-c", "alembic upgrade head && gunicorn -w 2 -k uvicorn.workers.UvicornWorker app.main:app --bind 0.0.0.0:8000 --timeout 120 --worker-connections 1000"]
