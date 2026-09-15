FROM docker.io/library/ubuntu:24.04

ARG IHP_PDK_REV=8d3ee38d4540ed675d3ac08332a51f75258fc3a7
ARG OPENVAF_VERSION=23_5_0
ARG OPENVAF_SHA256=79c0e08ad948a7a9f460dc87be88b261bbd99b63a4038db3c64680189f44e4f0
ARG MAGIC_VERSION=8.3.664
ARG MAGIC_REV=381714e2d5debf2ded71c5a6b6604e6b936422cf
ARG NETGEN_REV=e1528a797cdb155d6ebf8d91c5a55ed7d1713156

LABEL org.opencontainers.image.title="LeetSpice" \
      org.opencontainers.image.description="Gamified analog circuit design platform"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive \
    TZ=Etc/UTC \
    PATH="/opt/venv/bin:/home/leetspice/.local/bin:${PATH}"

RUN apt-get update \
    && apt-get install --no-install-recommends --yes adduser autoconf automake binutils build-essential ca-certificates curl git libx11-dev libxext-dev libxrender-dev libxpm-dev m4 ngspice python3 python3-tk python3-venv tcl-dev tk-dev xschem \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/venv \
    && addgroup --system leetspice \
    && adduser --system --ingroup leetspice --home /home/leetspice leetspice

WORKDIR /app

COPY pyproject.toml README.md alembic.ini ./
COPY src ./src
COPY migrations ./migrations
COPY challenges ./challenges
COPY scripts ./scripts

RUN python -m pip install --no-cache-dir '.[eda]' \
    && test "$(python -c 'import klayout; print(klayout.__version__)')" = "0.30.3" \
    && git clone --filter=blob:none --no-checkout https://github.com/RTimothyEdwards/magic.git /tmp/magic \
    && git -C /tmp/magic fetch --depth 1 origin "${MAGIC_REV}" \
    && git -C /tmp/magic checkout --detach "${MAGIC_REV}" \
    && cd /tmp/magic \
    && ./configure --prefix=/usr/local --with-tcl=/usr/lib --with-tk=/usr/lib \
    && make \
    && make install \
    && cd /app \
    && rm -rf /tmp/magic \
    && git clone --filter=blob:none --no-checkout https://github.com/RTimothyEdwards/netgen.git /tmp/netgen \
    && git -C /tmp/netgen fetch --depth 1 origin "${NETGEN_REV}" \
    && git -C /tmp/netgen checkout --detach "${NETGEN_REV}" \
    && cd /tmp/netgen \
    && ./configure --prefix=/usr/local \
    && make \
    && make install \
    && cd /app \
    && rm -rf /tmp/netgen \
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
    && chown -R root:root /app \
    && chmod -R 555 /app \
    && chown -R leetspice:leetspice /var/lib/leetspice \
    && chmod -R a-w /opt/IHP-Open-PDK \
    && apt-get purge --yes --auto-remove build-essential autoconf automake binutils git curl m4 \
    && rm -rf /var/lib/apt/lists/*

USER leetspice

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "leetspice.main:app", "--host", "0.0.0.0", "--port", "8000"]
