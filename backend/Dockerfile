FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/home/nugz \
    DATA_DIR=/data

RUN useradd --create-home --uid 10002 nugz \
 && mkdir -p /data && chown nugz:nugz /data
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# OpenBB genere ses routeurs au premier import (~30 s), dans site-packages :
# on le fait au build, en root, pour que le conteneur demarre instantanement.
RUN python -c "from openbb import obb"

COPY --chown=nugz:nugz app ./app
USER nugz

# Le journal des decisions vit ici (volume Docker) : il survit aux redemarrages.
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status==200 else 1)"

# Un seul worker : cache, planificateur et journal vivent dans le process.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
