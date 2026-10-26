# Imagem de produção: o painel é compilado e servido pelo próprio backend.
#
# Por que Docker aqui, se a regra do projeto é não usar Docker: a regra existe porque o SSD da
# máquina do dono está apertado. Esta imagem é construída NO RENDER — não ocupa um byte da máquina
# dele. E resolve o problema real de um serviço só que precisa de duas cadeias de ferramentas:
# Node para compilar o painel, Python para servir. No runtime nativo do Render isso dependeria de o
# Node estar presente na imagem de build deles, que é uma promessa que não está no nosso controle.
#
# O desenvolvimento continua sem Docker: scripts\dev.ps1 e scripts\web.ps1, como sempre.

# ---------------------------------------------------------------- painel (Node)
# Mesma versão do CI: se o build passar lá e quebrar aqui, o culpado não pode ser a versão do Node.
FROM node:24-slim AS painel

WORKDIR /web
# package*.json primeiro: enquanto as dependências não mudarem, esta camada vem do cache e o
# `npm ci` (o passo lento) não roda de novo a cada commit de código
COPY web/package.json web/package-lock.json ./
RUN npm ci

COPY web/ ./
# `npm run build` roda `tsc -b` antes do vite: erro de tipo derruba o deploy aqui, não no navegador
RUN npm run build


# ---------------------------------------------------------------- servidor (Python)
FROM python:3.11-slim AS servidor

# PYTHONDONTWRITEBYTECODE: contêiner efêmero não ganha nada com .pyc no disco
# PYTHONUNBUFFERED: sem isto o log do uvicorn fica preso no buffer e o painel do Render mostra
#   as linhas em blocos atrasados — justamente quando se está olhando por causa de um problema
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app/backend

# Todas as dependências têm wheel binário (psycopg-binary inclusive), então não é preciso
# compilador nenhum na imagem — o que a mantém pequena e sem ferramenta de build em produção.
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./

# O layout precisa bater com WEB_DIST_DIR ("../web/dist", relativo a backend/): com o backend em
# /app/backend, o painel tem de ficar em /app/web/dist. Mudar um sem o outro faz o servidor subir
# saudável servindo 404 na raiz — o painel simplesmente não aparece, e a API responde normal.
COPY --from=painel /web/dist /app/web/dist

# Usuário sem privilégio: se um dia algo escapar do processo, escapa sem root.
RUN useradd --create-home --shell /usr/sbin/nologin kadosh && chown -R kadosh:kadosh /app
USER kadosh

EXPOSE 8000

# O Render injeta PORT; o padrão cobre `docker run` local sem variável nenhuma.
# Um worker só de propósito: o SQLAlchemy aqui é síncrono e a loja tem dois usuários — mais
# workers só multiplicariam conexões no Postgres sem ninguém para atender.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --proxy-headers --forwarded-allow-ips '*'"]
