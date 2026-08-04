FROM docker.io/library/python:3.12-slim

ARG IHP_PDK_REV=8d3ee38d4540ed675d3ac08332a51f75258fc3a7
ARG OPENVAF_VERSION=23_5_0
ARG OPENVAF_SHA256=79c0e08ad948a7a9f460dc87be88b261bbd99b63a4038db3c64680189f44e4f0

LABEL org.opencontainers.image.title="LeetSpice" \
      org.opencontainers.image.description="Gamified analog circuit design platform"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/home/leetspice/.local/bin:${PATH}"

RUN apt-get update \
    && apt-get install --no-install-recommends --yes binutils ca-certificates curl git ngspice xschem \
    && rm -rf /var/lib/apt/lists/* \
    && addgroup --system leetspice \
    && adduser --system --ingroup leetspice --home /home/leetspice leetspice

WORKDIR /app

COPY pyproject.toml README.md alembic.ini ./
COPY src ./src
COPY migrations ./migrations
COPY challenges ./challenges
COPY scripts ./scripts

RUN python -m pip install --no-cache-dir '.[eda]' \
    && curl --fail --location "https://openva.fra1.cdn.digitaloceanspaces.com/openvaf_${OPENVAF_VERSION}_linux_amd64.tar.gz" --output /tmp/openvaf.tar.gz \
    && echo "${OPENVAF_SHA256}  /tmp/openvaf.tar.gz" | sha256sum --check \
    && tar -xzf /tmp/openvaf.tar.gz -C /usr/local/bin \
    && rm /tmp/openvaf.tar.gz \
    && git clone --filter=blob:none --no-checkout https://github.com/IHP-GmbH/IHP-Open-PDK.git /opt/IHP-Open-PDK \
    && git -C /opt/IHP-Open-PDK fetch --depth 1 origin "${IHP_PDK_REV}" \
    && git -C /opt/IHP-Open-PDK checkout --detach "${IHP_PDK_REV}" \
    && rm -rf /opt/IHP-Open-PDK/.git \
    && cd /opt/IHP-Open-PDK/ihp-sg13g2/libs.tech/verilog-a \
    && ./openvaf-compile-va.sh \
    && test -s ../ngspice/osdi/psp103.osdi \
    && test -s ../ngspice/osdi/psp103_nqs.osdi \
    && test -s ../ngspice/osdi/r3_cmc.osdi \
    && test -s ../ngspice/osdi/mosvar.osdi \
    && cd /app \
    && mkdir -p /var/lib/leetspice \
    && chown -R leetspice:leetspice /app /var/lib/leetspice \
    && chmod -R a-w /opt/IHP-Open-PDK

USER leetspice

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "leetspice.main:app", "--host", "0.0.0.0", "--port", "8000"]
