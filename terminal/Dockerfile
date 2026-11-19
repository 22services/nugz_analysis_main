FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/home/terminal

RUN useradd --create-home --uid 10002 terminal
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# OpenBB genere ses routeurs au premier import (~30 s), dans site-packages :
# on le fait au build, en root, pour que le conteneur demarre instantanement.
RUN python -c "from openbb import obb"

USER terminal

COPY --chown=terminal:terminal app.py .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/terminal/health', timeout=4).status==200 else 1)"

# Un seul worker : le cache TTL est en memoire du process.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
