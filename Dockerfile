FROM python:3.12-slim

# Git es necesario para las operaciones de git_commit, git_push, etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Configurar git para Mikalia
RUN git config --global user.name "Mikalia" && \
    git config --global user.email "mikalia@mikata-ai-lab.com"

WORKDIR /app

# Instalar dependencias primero (cache de Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el proyecto
COPY . .

# Crear directorios necesarios
RUN mkdir -p data logs

# Variables de entorno requeridas (se pasan en docker run o docker-compose)
# ANTHROPIC_API_KEY=sk-ant-...
# TELEGRAM_BOT_TOKEN=...
# TELEGRAM_CHAT_ID=...

ENTRYPOINT ["python", "-m", "mikalia"]
CMD ["chat", "--core"]
