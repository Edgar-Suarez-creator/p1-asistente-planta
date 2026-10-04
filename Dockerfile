# Construir desde la carpeta que contiene planta-core/ y p1-asistente-planta/:
#   docker build -f p1-asistente-planta/Dockerfile -t p1-asistente-planta .
FROM python:3.11-slim
WORKDIR /srv
COPY planta-core /srv/planta-core
COPY p1-asistente-planta /srv/p1-asistente-planta
RUN pip install --no-cache-dir -e /srv/planta-core -e "/srv/p1-asistente-planta[dev]" \
 && cd /srv/planta-core && python -m planta_core.generar
WORKDIR /srv/p1-asistente-planta
RUN python -m app.servidor --exportar
EXPOSE 8001
CMD ["python", "-c", "import app.servidor as s, http.server as h; h.ThreadingHTTPServer(('0.0.0.0', 8001), s.Manejador).serve_forever()"]
