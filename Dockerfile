# Imagen del backend de LoR Guru.
#
# Decisión de despliegue (GUIA_FASE3.md §6): el índice vectorial se HORNEA en
# la imagen durante el build — el RUN de build_index descarga los datos de
# cartas, baja el modelo de embeddings (queda en la caché de HF de la imagen)
# y construye chroma_db/. El contenedor arranca sirviendo, nunca
# construyendo: si el índice faltara, la API falla al arrancar por diseño.
# Alternativa documentada en la guía: volumen persistente + job de build.
FROM python:3.12-slim

WORKDIR /app

# Torch CPU explícito ANTES de requirements: la variante por defecto trae
# CUDA (~3 GB extra que un servidor sin GPU no usa).
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

COPY lorguru/ lorguru/

# Hornea datos + modelo + índice en la imagen (~3 GB por el modelo e5).
RUN python -m lorguru.build_index

# ORIGENES_CORS se define en el host (el dominio real de Vercel).
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn lorguru.api:app --host 0.0.0.0 --port ${PORT}"]
