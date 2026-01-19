FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN python -m pip install --no-cache-dir uv

COPY pyproject.toml ./
COPY uv.lock ./

# 依存を .venv に同期
RUN uv sync --frozen --no-dev

COPY . .

# .venv の uvicorn をそのまま使えるようにする
ENV PATH="/app/.venv/bin:${PATH}" \
    HOST=0.0.0.0 \
    PORT=8000 \
    APP_MODULE=app.main:app

EXPOSE 8000

CMD ["sh", "-c", "uvicorn ${APP_MODULE} --host ${HOST} --port ${PORT}"]
