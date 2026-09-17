FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1

WORKDIR /app

# System libraries for the geospatial stack (GeoPandas / pyogrio / shapely) and
# curl for the container healthcheck. GDAL/GEOS/PROJ are needed to read the BBS
# shapefiles and reproject them; the core API image stays free of all this.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        gdal-bin libgdal-dev \
        libgeos-dev \
        libproj-dev \
        libspatialindex-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

EXPOSE 8000
# GIS warm-load takes a while on boot, so give /health a generous start period.
HEALTHCHECK --interval=30s --timeout=5s --start-period=180s --retries=5 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
