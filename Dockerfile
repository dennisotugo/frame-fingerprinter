# syntax=docker/dockerfile:1
# ---------------------------------------------------------------------------
# Stage 1 – Runtime image
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# System dependencies: ffmpeg + gnupg
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        gnupg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency manifests first for better layer caching
COPY requirements.txt pyproject.toml ./
COPY frame_fingerprinter/ ./frame_fingerprinter/
COPY fingerprint_video.py verify_video.py ./
COPY README.md ./

RUN pip install --no-cache-dir .

# Default GPG home inside the container (mount a real one via -v at runtime)
ENV GNUPGHOME=/root/.gnupg
VOLUME ["/data", "/root/.gnupg"]

WORKDIR /data

ENTRYPOINT ["python", "-m", "frame_fingerprinter"]
CMD ["--help"]

# ---------------------------------------------------------------------------
# Stage 2 – Development / CI image (adds test dependencies)
# ---------------------------------------------------------------------------
FROM runtime AS dev

COPY requirements-dev.txt ./
RUN pip install --no-cache-dir -r /app/requirements-dev.txt

COPY tests/ /app/tests/
WORKDIR /app

CMD ["python", "-m", "pytest", "tests/", "-v"]
