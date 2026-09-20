from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    models_dir: Path = Path("/models")
    model_repo: str = "mradermacher/Qwen3-0.6B-heretic-abliterated-uncensored-i1-GGUF"
    model_filename: str = "Qwen3-0.6B-heretic-abliterated-uncensored.i1-Q4_K_M.gguf"

    llama_n_ctx: int = 4096
    llama_n_gpu_layers: int = 0
    llama_threads: int = 4
    llama_n_batch: int = 512
    llama_chat_format: Optional[str] = None
    llama_verbose: bool = False

    preload_model: bool = True
    max_tool_iterations: int = 3

    mcp_enabled: bool = True
    mcp_timeout: float = 120.0
    mcp_servers: str = ""

    openrouter_api_key: str = ""
    openrouter_model: str = "openrouter/free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_timeout: float = 120.0
    openrouter_http_referer: str = "https://localhost"
    openrouter_app_name: str = "LLMPersonalAssistant"
    tool_routing_rules: Optional[str] = None

    @property
    def model_path(self) -> Path:
        return self.models_dir / self.model_filename

    @property
    def has_openrouter_key(self) -> bool:
        return bool(self.openrouter_api_key.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()