from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic.alias_generators import to_camel
from sqlalchemy import text

from app.api.routes import api_router
from app.core.config import get_settings
from app.db.session import engine
from app.services.errors import DomainError

settings = get_settings()

app = FastAPI(title=settings.app_name, version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@app.middleware("http")
async def require_csrf_header(request: Request, call_next):
    """Defensa CSRF para la cookie de sesión: toda escritura debe traer una cabecera propia.

    Un formulario de otro sitio no puede enviarla, y un fetch de otro origen la dispara en
    un preflight CORS que solo aprueban los orígenes permitidos.
    """
    if (
        request.method in UNSAFE_METHODS
        and request.url.path.startswith(settings.api_prefix)
        and request.headers.get("X-Requested-With") != "fetch"
    ):
        return JSONResponse(
            status_code=403,
            content={"detail": "Solicitud rechazada (falta cabecera).", "code": "csrf"},
        )
    return await call_next(request)


@app.exception_handler(DomainError)
async def domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.message,
            "code": exc.code,
            **{to_camel(k): v for k, v in exc.extra.items()},
        },
    )


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    with engine.connect() as conn:
        conn.execute(text("select 1"))
    return {"status": "ok"}


app.include_router(api_router, prefix=settings.api_prefix)
