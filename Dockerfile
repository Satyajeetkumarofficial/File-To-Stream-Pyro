FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    MALLOC_ARENA_MAX=2

RUN apt-get update \
 && apt-get install -y --no-install-recommends git gcc libc6-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /rexbots
ARG REQS=requirements.txt
COPY requirements*.txt ./
RUN pip install -U pip && pip install -U -r ${REQS}

COPY . .
CMD ["python", "bot.py"]
