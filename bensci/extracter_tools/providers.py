"""LLM provider presets and resolution helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Sequence


@dataclass
class ProviderSettings:
    """HTTP settings required to talk to an LLM provider."""

    provider: str
    base_url: str
    chat_path: str = "/chat/completions"
    api_key_env: str = "OPENAI_API_KEY"
    api_key_header: str = "Authorization"
    api_key_prefix: str = "Bearer "
    response_path: Sequence[Any] = ("choices", 0, "message", "content")
    extra_headers: Dict[str, str] = field(default_factory=dict)

    @property
    def endpoint(self) -> str:
        return f"{self.base_url.rstrip('/')}{self.chat_path}"


PROVIDER_PRESETS: Dict[str, ProviderSettings] = {
    "openai": ProviderSettings(
        provider="openai",
        base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
    ),
    "chatanywhere": ProviderSettings(
        provider="chatanywhere",
        base_url="https://api.chatanywhere.tech/v1",
        api_key_env="CHAT_ANYWHERE_API_KEY",
    ),
    "dashscope": ProviderSettings(
        provider="dashscope",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key_env="DASHSCOPE_API_KEY",
    ),
    "deepseek": ProviderSettings(
        provider="deepseek",
        base_url="https://api.deepseek.com",
        api_key_env="DEEPSEEK_API_KEY",
    ),
    "moonshot": ProviderSettings(
        provider="moonshot",
        base_url="https://api.moonshot.ai/v1",
        api_key_env="MOONSHOT_API_KEY",
    ),
    "zhipu": ProviderSettings(
        provider="zhipu",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        chat_path="/chat/completions",
        api_key_env="ZHIPU_API_KEY",
    ),
    "baichuan": ProviderSettings(
        provider="baichuan",
        base_url="https://api.baichuan-ai.com/v1",
        api_key_env="BAICHUAN_API_KEY",
    ),
    "minimax": ProviderSettings(
        provider="minimax",
        base_url="https://api.minimax.io/v1",
        api_key_env="MINIMAX_API_KEY",
    ),
}


def resolve_provider_settings(
    provider: str,
    *,
    base_url: Optional[str] = None,
    chat_path: Optional[str] = None,
    api_key_env: Optional[str] = None,
    api_key_header: Optional[str] = None,
    api_key_prefix: Optional[str] = None,
) -> ProviderSettings:
    """Return configuration for a provider, applying optional overrides."""

    if not provider:
        raise ValueError(
            "LLM provider 未指定。请在 config.LLM_EXTRACTION_PROVIDER 设置 "
            "或通过命令行 --provider 显式传入。"
        )

    normalized = provider.lower()
    preset = PROVIDER_PRESETS.get(normalized)

    if preset is not None:
        settings = ProviderSettings(
            provider=preset.provider,
            base_url=preset.base_url,
            chat_path=preset.chat_path,
            api_key_env=preset.api_key_env,
            api_key_header=preset.api_key_header,
            api_key_prefix=preset.api_key_prefix,
            response_path=tuple(preset.response_path),
            extra_headers=dict(preset.extra_headers),
        )
    else:
        if not base_url or not api_key_env:
            raise ValueError(
                f"不支持的 LLM 厂家：{provider}。请在 config 中提供 LLM_EXTRACTION_BASE_URL "
                "与 LLM_EXTRACTION_API_KEY_ENV。"
            )
        settings = ProviderSettings(
            provider=provider,
            base_url=base_url,
            chat_path=chat_path or "/chat/completions",
            api_key_env=api_key_env,
            api_key_header=api_key_header or "Authorization",
            api_key_prefix=api_key_prefix if api_key_prefix is not None else "Bearer ",
        )

    if base_url:
        settings.base_url = base_url
    if chat_path:
        settings.chat_path = chat_path
    if api_key_env:
        settings.api_key_env = api_key_env
    if api_key_header:
        settings.api_key_header = api_key_header
    if api_key_prefix is not None:
        settings.api_key_prefix = api_key_prefix

    return settings
