FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.lock.txt .
RUN pip install --no-cache-dir --only-binary :all: --require-hashes -r requirements.lock.txt

COPY main.py alembic.ini openapi.yaml ./
COPY config/ config/
COPY controller/ controller/
COPY eventos/ eventos/
COPY migrations/ migrations/
COPY model/ model/
COPY scripts/ scripts/
COPY service/ service/

EXPOSE 8003

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --create-home --shell /usr/sbin/nologin app
USER app:app

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8003"]
