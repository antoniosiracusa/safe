FROM python:3.13-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# GeoDjango (GDAL/GEOS/PROJ) + WeasyPrint (M5) + build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
      gdal-bin libgdal32 libgeos-c1v5 libproj25 \
      libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libffi8 shared-mime-info fonts-dejavu-core \
      curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
RUN pip install -e ".[dev]" 2>/dev/null || true
COPY . .
RUN pip install -e ".[dev]"

RUN useradd --create-home --uid 1000 safe && chown -R safe:safe /app
USER safe

EXPOSE 8000
CMD ["gunicorn", "safe.wsgi:application", "-b", "0.0.0.0:8000", "-w", "4", "--timeout", "60"]
