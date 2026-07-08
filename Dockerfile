# Imagen del backend de LoR Guru.
#
# Decisión de despliegue (revisada tras migrar a embeddings de Gemini,
# 2026-07): el índice vectorial se CONSTRUYE LOCALMENTE antes del build de la
# imagen (`python -m lorguru.build_index`, que usa tus claves de Gemini) y se
# COPIA ya hecho. Ventajas frente a hornearlo en el build:
#   - No metemos claves de API en el build de Docker (el build necesitaría
#     GEMINI_API_KEY_*; un build no debe llevar secretos).
#   - El chroma_db/ resultante solo contiene vectores y metadata — NO secretos.
#   - La imagen ya no necesita torch ni sentence-transformers (~2.5 GB menos).
# El contenedor arranca sirviendo; si el índice no estuviera, la API falla al
# arrancar por diseño (separación indexado/servido de la fase 2).
#
# ANTES de `docker build`, en tu máquina:
#   python -m lorguru.build_index          # deja data/ y chroma_db/ listos
#
# En RUNTIME el servidor necesita GEMINI_API_KEY (para embeber las consultas)
# y ORIGENES_CORS — se pasan como variables de entorno del host, no en la
# imagen.
FROM python:3.12-slim

WORKDIR /app

COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

COPY lorguru/ lorguru/
# Artefactos ya construidos localmente (no secretos): datos de cartas + índice.
COPY data/ data/
COPY chroma_db/ chroma_db/

ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn lorguru.api:app --host 0.0.0.0 --port ${PORT}"]
