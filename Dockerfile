# syntax=docker/dockerfile:1

FROM python:3.11-slim AS runtime

ARG OPENET2_VERSION=1.6.0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLBACKEND=Agg \
    MPLCONFIGDIR=/tmp/matplotlib \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY examples ./examples
COPY docker/legacy_code /code

RUN python -m pip install --upgrade pip \
    && python -m pip install ".[video]" \
    && python -c "from importlib.metadata import version; assert version('openet2') == '${OPENET2_VERSION}'"

RUN useradd --create-home --uid 10001 openet2 \
    && mkdir -p /data /output /tmp/matplotlib \
    && chown -R openet2:openet2 /data /output /tmp/matplotlib

USER openet2

ENTRYPOINT ["openet2"]
CMD ["--help"]

FROM runtime AS test

USER root
RUN python -m pip install "pytest>=8"
COPY tests ./tests
RUN chown -R openet2:openet2 /app/tests
USER openet2

ENTRYPOINT ["python", "-m", "pytest"]
CMD ["-q", "-p", "no:cacheprovider"]
