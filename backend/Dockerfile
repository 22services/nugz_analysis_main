FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Les dependances d'abord : cette couche est mise en cache tant que
# requirements.txt ne bouge pas.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Pas de root dans le conteneur.
RUN useradd --create-home --uid 10001 comite && chown -R comite:comite /app
USER comite

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status==200 else 1)"

# 8 vCPU sur le VPS, mais le pipeline est I/O bound (appels LLM a venir) :
# 2 workers suffisent largement et laissent la marge au reste de l'infra.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
