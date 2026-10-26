"""Aplicação FastAPI: API em /api/v1 e, quando existir o build, o painel web em /.

Segurança aplicada aqui (desde a fase 1): cabeçalhos de proteção, limite de corpo (inclusive chunked),
limite de tentativas, documentação desligada em produção, erros de integridade classificados.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from sqlalchemy.exc import IntegrityError
from starlette.datastructures import Headers
from starlette.middleware.base import BaseHTTPMiddleware

from app import __version__
from app.api.v1.router import api_router
from app.bootstrap import bootstrap_admin_resiliente
from app.core.config import get_settings
from app.core.limiter import limiter

settings = get_settings()
log = logging.getLogger("kadosh.http")

# Fontes da marca são self-hosted no painel (@fontsource) — a CSP não abre para domínios externos.
# O build do Vite/Tailwind v4 não tem <style> nem style="" inline, então style-src fica em 'self'.
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; "
    "img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; "
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)

# Mensagens de validação em português (o Pydantic fala inglês).
VALIDATION_MESSAGES = {
    "missing": "Campo obrigatório.",
    "string_too_short": "Texto curto demais.",
    "string_too_long": "Texto longo demais.",
    "string_type": "Informe um texto.",
    "int_parsing": "Informe um número inteiro.",
    "int_type": "Informe um número inteiro.",
    "bool_parsing": "Informe verdadeiro ou falso.",
    "less_than_equal": "Valor acima do permitido.",
    "greater_than_equal": "Valor abaixo do permitido.",
    "extra_forbidden": "Campo não reconhecido.",
    "json_invalid": "JSON inválido.",
    "literal_error": "Valor não permitido.",
    "enum": "Valor não permitido.",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("X-Frame-Options", "DENY")
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")  # JSON autenticado não fica em cache
        elif request.url.path.startswith("/assets/"):
            # nomes com hash do Vite: imutáveis (index.html continua no-cache)
            response.headers.setdefault("Cache-Control", "public, max-age=31536000, immutable")
        else:
            response.headers.setdefault("Content-Security-Policy", CSP)
        if settings.is_production:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response


class BodySizeLimitMiddleware:
    """Responde 413 para corpos acima do limite — pelo Content-Length ou contando os bytes (chunked)."""

    def __init__(self, app, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        length = Headers(scope=scope).get("content-length")
        if length and length.isdigit() and int(length) > self.max_bytes:
            response = JSONResponse({"detail": "Requisição grande demais."}, status_code=413)
            return await response(scope, receive, send)

        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise HTTPException(413, "Requisição grande demais.")
            return message

        await self.app(scope, limited_receive, send)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Sobe o serviço. O bootstrap do admin NÃO pode impedir isso.

    Aconteceu no primeiro deploy: o serviço subiu antes de o Postgres recém-criado aceitar conexão,
    `bootstrap_admin` estourou `OperationalError`, o uvicorn abortou e o deploy foi reprovado. O
    banco ficou pronto trinta segundos depois — não havia nada errado além da ordem.

    Duas decisões aqui:
    - Tenta de novo por um tempo curto: reinício por manutenção do Render costuma reencontrar o
      banco em segundos, e desistir na primeira recusa transformaria um soluço em indisponibilidade.
    - Se ainda assim não conectar, LOGA e segue. Criar o primeiro administrador é conveniência de
      primeira subida, não pré-requisito para servir; a tabela continua vazia e a próxima subida
      tenta de novo. Quem denuncia banco fora é o /health, que o Render já consulta — e aí o
      diagnóstico é "banco indisponível", não um processo que morreu sem explicar por quê.
    """
    bootstrap_admin_resiliente()
    yield


def create_app() -> FastAPI:
    docs_enabled = settings.DOCS_ENABLED and not settings.is_production
    app = FastAPI(
        title=settings.APP_NAME,
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs" if docs_enabled else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if docs_enabled else None,
    )
    app.state.limiter = limiter
    # Ordem: o último adicionado é o mais externo — cabeçalhos de segurança envolvem tudo, inclusive o 413.
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.MAX_BODY_BYTES)
    app.add_middleware(SecurityHeadersMiddleware)

    @app.exception_handler(RateLimitExceeded)
    async def _rate_limited(request: Request, exc: RateLimitExceeded):
        return JSONResponse(
            {"detail": "Muitas tentativas. Aguarde um minuto."}, status_code=429, headers={"Retry-After": "60"}
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        """422 em português e sem ecoar o corpo enviado (o padrão devolve `input`, inclusive senha)."""
        out = []
        for e in exc.errors():
            msg = VALIDATION_MESSAGES.get(e["type"]) or str(e.get("msg", "")).removeprefix("Value error, ")
            if msg.startswith("value is not a valid email"):
                msg = "E-mail inválido."
            out.append({"loc": [p for p in e["loc"] if p != "body"], "msg": msg, "type": e["type"]})
        return JSONResponse({"detail": out}, status_code=422)

    @app.exception_handler(IntegrityError)
    async def _integrity(request: Request, exc: IntegrityError):
        code = getattr(exc.orig, "sqlstate", None)
        if code == "23505":
            return JSONResponse({"detail": "Já existe um registro com esses dados."}, status_code=409)
        if code == "23503":
            return JSONResponse(
                {"detail": "O registro possui histórico e não pode ser excluído; arquive em vez de excluir."},
                status_code=409,
            )
        if code in ("23514", "23502"):
            return JSONResponse({"detail": "Valor inválido para esta operação."}, status_code=422)
        log.error("IntegrityError não classificado em %s %s", request.method, request.url.path, exc_info=exc)
        return JSONResponse({"detail": "Erro interno."}, status_code=500)

    app.include_router(api_router)
    _mount_web(app)
    return app


def _mount_web(app: FastAPI) -> None:
    """Serve o painel web (build do Vite) quando a pasta existir. Rotas /api/* nunca caem aqui."""
    dist = (Path(__file__).resolve().parent.parent / settings.WEB_DIST_DIR).resolve()
    index = dist / "index.html"
    if not index.exists():
        return

    assets = dist / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse({"detail": "Rota não encontrada."}, status_code=404)
        # Confinado a `dist`: `..` ou caminhos absolutos nunca saem da pasta do painel.
        candidate = (dist / full_path).resolve()
        if full_path and candidate.is_relative_to(dist) and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})


app = create_app()
