FROM docker.io/library/python:3.12-slim

LABEL org.opencontainers.image.title="LeetSpice" \
      org.opencontainers.image.description="Gamified analog circuit design platform"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/home/leetspice/.local/bin:${PATH}"

RUN apt-get update \
    && apt-get install --no-install-recommends --yes ngspice \
    && rm -rf /var/lib/apt/lists/* \
    && addgroup --system leetspice \
    && adduser --system --ingroup leetspice --home /home/leetspice leetspice

WORKDIR /app

COPY pyproject.toml README.md alembic.ini ./
COPY src ./src
COPY migrations ./migrations
COPY challenges ./challenges
COPY scripts ./scripts

RUN python -m pip install --no-cache-dir . \
    && mkdir -p /var/lib/leetspice \
    && chown -R leetspice:leetspice /app /var/lib/leetspice

USER leetspice

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "leetspice.main:app", "--host", "0.0.0.0", "--port", "8000"]
