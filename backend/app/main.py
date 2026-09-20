from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from huggingface_hub import hf_hub_download

from .config import get_settings
from .llm import get_engine
from .mcp_manager import register_mcp_tools, shutdown_mcp
from .routers import assistant, chat, reasoning
from .tools.builtin import registry


def ensure_model_downloaded(settings) -> None:
    settings.models_dir.mkdir(parents=True, exist_ok=True)
    if settings.model_path.is_file() and settings.model_path.stat().st_size > 0:
        return
    hf_hub_download(
        repo_id=settings.model_repo,
        filename=settings.model_filename,
        local_dir=str(settings.models_dir),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    ensure_model_downloaded(settings)
    if settings.mcp_enabled:
        register_mcp_tools(settings)
    if settings.preload_model:
        get_engine(settings).load()
    yield
    shutdown_mcp()


app = FastAPI(title="LLM Personal Assistant", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(assistant.router)
app.include_router(reasoning.router)


@app.get("/")
def root() -> dict:
    return {"service": "llm-assistant", "routes": ["/chat", "/assistant", "/reasoning", "/models", "/health"]}


@app.get("/health")
def health() -> dict:
    from .mcp_manager import mcp_status

    settings = get_settings()
    engine = get_engine(settings)
    return {
        "status": "ok",
        "model_repo": settings.model_repo,
        "model_filename": settings.model_filename,
        "model_file": str(settings.model_path),
        "model_downloaded": settings.model_path.is_file(),
        "model_ready": engine.loaded(),
        "openrouter_enabled": settings.has_openrouter_key,
        "openrouter_model": settings.openrouter_model,
        "tools": [t["name"] for t in registry.schemas()],
        "mcp": mcp_status(),
    }