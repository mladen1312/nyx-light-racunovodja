FROM python:3.12-slim

LABEL maintainer="Dr. Mladen Mešter <mladen@nexellum.com>"
LABEL description="Nyx Light — Računovođa: AI sustav za računovodstvo RH"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    NYX_HOST=0.0.0.0 \
    NYX_PORT=7860 \
    NYX_WORKERS=4

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
EXPOSE 8000

CMD ["python", "-m", "nyx_light.main", "--host", "0.0.0.0", "--port", "8000"]
