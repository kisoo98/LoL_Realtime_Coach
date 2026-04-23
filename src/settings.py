"""Configuration loading with pydantic validation."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Tuple

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator


class AppCfg(BaseModel):
    hotkey: str = "f9"
    buffer_seconds: int = 60
    loop_target_fps: int = 30
    language: str = "ko"
    debug_overlay: bool = False
    # Which LLM provider to use for feedback: "grok" | "gemini"
    llm_provider: str = "gemini"


class ResolutionCfg(BaseModel):
    minimap_bbox: Tuple[int, int, int, int]


class CaptureCfg(BaseModel):
    active_resolution: str
    resolutions: Dict[str, ResolutionCfg]

    def active_bbox(self) -> Tuple[int, int, int, int]:
        if self.active_resolution not in self.resolutions:
            raise ValueError(
                f"Resolution {self.active_resolution} not configured."
            )
        return self.resolutions[self.active_resolution].minimap_bbox


class YoloCfg(BaseModel):
    model_path: str
    conf_threshold: float = 0.35
    iou_threshold: float = 0.5
    device: str = "cuda:0"
    classes: List[str]


class GrokCfg(BaseModel):
    base_url: str = "https://api.x.ai/v1"
    model: str = "grok-4.20-vision"
    max_tokens: int = 600
    temperature: float = 0.4
    timeout_seconds: int = 8


class GeminiCfg(BaseModel):
    model: str = "gemini-2.5-pro"
    max_tokens: int = 600
    temperature: float = 0.4
    timeout_seconds: int = 15


class LoggingCfg(BaseModel):
    level: str = "INFO"
    file: str = "logs/coach.log"


class Settings(BaseModel):
    app: AppCfg
    capture: CaptureCfg
    yolo: YoloCfg
    grok: GrokCfg
    gemini: GeminiCfg = Field(default_factory=GeminiCfg)
    logging: LoggingCfg

    # Loaded from .env, not yaml
    xai_api_key: str = Field(default="")
    gemini_api_key: str = Field(default="")


def load_settings(
    config_path: str | Path = "configs/config.yaml",
    env_path: str | Path = ".env",
) -> Settings:
    load_dotenv(env_path)
    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    raw["xai_api_key"] = os.getenv("XAI_API_KEY", "")
    raw["gemini_api_key"] = os.getenv("GEMINI_API_KEY", "")
    return Settings.model_validate(raw)
