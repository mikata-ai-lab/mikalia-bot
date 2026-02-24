FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Usuario no-root para produccion
RUN useradd --create-home --shell /bin/bash mikalia

# Copiar dependencias instaladas
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

WORKDIR /app

# Configurar git para Mikalia
RUN git config --global user.name "Mikalia" && \
    git config --global user.email "mikalia@mikata-ai-lab.com"

# Copiar el proyecto
COPY . .

# Crear directorios con permisos correctos
RUN mkdir -p data logs && chown -R mikalia:mikalia /app

USER mikalia

EXPOSE 8000

ENTRYPOINT ["python", "-m", "mikalia"]
CMD ["chat", "--core"]
