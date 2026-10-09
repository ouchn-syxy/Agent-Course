"""
LLM 客户端封装（OpenAI SDK 兼容格式）。

与项目其他章节的 LLMClient 保持一致的接口风格：
显式参数传入，与配置文件解耦。
"""

from collections.abc import Iterable
from typing import Any

from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam


class LLMClient:
    """统一的 LLM 客户端，封装 OpenAI SDK 调用。"""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        temperature: float = 0.8,
        top_p: float = 0.95,
        max_tokens: int = 1024,
    ) -> None:
        self._model: str = model
        self._temperature: float = temperature
        self._top_p: float = top_p
        self._max_tokens: int = max_tokens

        self._client: OpenAI = OpenAI(
            api_key=api_key,
            base_url=base_url,
        )

    @property
    def model(self) -> str:
        return self._model

    def chat(
        self,
        messages: Iterable[ChatCompletionMessageParam],
        **kwargs: Any,
    ) -> str:
        """发送消息并返回模型文本回复。"""
        completion = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=kwargs.get("temperature", self._temperature),
            top_p=kwargs.get("top_p", self._top_p),
            max_tokens=kwargs.get("max_tokens", self._max_tokens),
        )
        return completion.choices[0].message.content or ""
