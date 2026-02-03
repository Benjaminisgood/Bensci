"""Generic HTTP client for ChatCompletion-like LLM endpoints."""

from __future__ import annotations

import os
from typing import Any, Mapping, Optional

import requests

from .providers import ProviderSettings


class LLMClient:
    """Lightweight client that works with multiple provider presets."""

    def __init__(
        self,
        *,
        settings: ProviderSettings,
        model: str,
        system_prompt: str,
        temperature: float = 0.1,
        timeout: int = 120,
    ) -> None:
        self.settings = settings
        self.model = model
        self.system_prompt = system_prompt
        self.temperature = temperature
        self.timeout = timeout

    @property
    def api_key(self) -> Optional[str]:
        return os.getenv(self.settings.api_key_env)

    @property
    def is_available(self) -> bool:
        return bool(self.api_key)

    def generate(self, user_prompt: str) -> str:
        api_key = self.api_key
        if not api_key:
            raise RuntimeError(
                "环境变量 %s 未配置，无法调用 %s LLM。"
                % (self.settings.api_key_env, self.settings.provider)
            )

        url = self.settings.endpoint
        headers = {"Content-Type": "application/json"}
        if self.settings.api_key_header:
            headers[self.settings.api_key_header] = f"{self.settings.api_key_prefix or ''}{api_key}"
        if self.settings.extra_headers:
            headers.update(self.settings.extra_headers)

        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        response = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
        if response.status_code != 200:
            raise RuntimeError(
                "%s API 调用失败：status=%s body=%s"
                % (
                    self.settings.provider,
                    response.status_code,
                    response.text[:500],
                )
            )

        data = response.json()
        try:
            return self._extract_content(data)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"LLM 响应结构异常：{data}") from exc

    def _extract_content(self, payload: Mapping[str, Any]) -> str:
        value: Any = payload
        for key in self.settings.response_path:
            if isinstance(key, int):
                if not isinstance(value, list):
                    raise KeyError(key)
                value = value[key]
            else:
                if not isinstance(value, Mapping):
                    raise KeyError(key)
                value = value[key]

        if not isinstance(value, str):
            raise TypeError("LLM 响应内容不是字符串")
        return value
