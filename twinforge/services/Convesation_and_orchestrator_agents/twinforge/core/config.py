"""
TWINFORGE — Centralized configuration via pydantic-settings.
Loads settings from .env file and environment variables.
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application-wide settings loaded from .env"""
    
    # ── LLM (Groq / Gemini) ──────────────────────────────────
    groq_api_key: str = Field(default="", description="Groq API key")
    groq_model: str = Field(default="llama-3.3-70b-versatile", description="Groq model name")
    gemini_api_key: str = Field(default="", description="Gemini API key")
    
    # ── Security ─────────────────────────────────────────
    tenant_id: str = Field(default="default", description="Tenant namespace for isolation")
    max_input_tokens: int = Field(default=2048, description="Max user input length in chars")
    rate_limit_per_min: int = Field(default=10, description="Max requests per minute per session")
    jwt_expiry_hours: int = Field(default=1, description="JWT session token expiry")
    
    # ── Observability ────────────────────────────────────
    log_level: str = Field(default="INFO", description="Logging level")
    
    # ── Paths ────────────────────────────────────────────
    project_root: Path = Field(default_factory=lambda: Path(__file__).resolve().parent.parent.parent)
    data_dir: Optional[Path] = Field(default=None)
    aasx_dir: Optional[Path] = Field(default=None)
    knowledge_base_dir: Optional[Path] = Field(default=None)
    
    # ── Agent Limits ─────────────────────────────────────
    max_tool_chain_depth: int = Field(default=5, description="Max tool chain depth to prevent loops")
    
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}
    
    def model_post_init(self, __context):
        if self.data_dir is None:
            self.data_dir = self.project_root / "data"
        if self.aasx_dir is None:
            self.aasx_dir = self.data_dir / "aasx"
        if self.knowledge_base_dir is None:
            self.knowledge_base_dir = self.data_dir / "knowledge_base"
        # Ensure directories exist
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.aasx_dir.mkdir(parents=True, exist_ok=True)
        self.knowledge_base_dir.mkdir(parents=True, exist_ok=True)


# ── Singleton ────────────────────────────────────────────
_settings: Optional[Settings] = None

def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
