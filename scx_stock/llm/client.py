"""
@description LLM 客户端封装，基于 OpenAI 兼容接口，支持 GLM / DeepSeek 切换。

通过 SCX_LLM_PROVIDER / SCX_LLM_BASE_URL / SCX_LLM_MODEL 环境变量配置，
两个提供商均兼容 OpenAI Chat Completions API，统一用 openai SDK 调用。
"""

import logging

from openai import AsyncOpenAI

from scx_stock.config.settings import get_settings

logger = logging.getLogger(__name__)

# 默认 base_url 与 model 预设，避免用户漏配时无提示
_PROVIDER_DEFAULTS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    },
    "glm": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4-flash",
    },
}


class LlmClient:
    """LLM 客户端，封装 OpenAI 兼容调用。

    使用 AsyncOpenAI，调用方在异步上下文中使用。
    """

    def __init__(self) -> None:
        s = get_settings()
        defaults = _PROVIDER_DEFAULTS.get(s.llm_provider, {})
        self.base_url = s.llm_base_url or defaults["base_url"]
        self.model = s.llm_model or defaults["model"]
        self.timeout = s.llm_timeout
        self._api_key = s.llm_api_key
        self._client: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        """懒加载 AsyncOpenAI 客户端。

        :returns: AsyncOpenAI 实例。
        """
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self._api_key,
                base_url=self.base_url,
                timeout=self.timeout,
            )
        return self._client

    @property
    def available(self) -> bool:
        """LLM 是否可用（已配置 API Key）。

        :returns: api_key 非空时为 True。
        """
        return bool(self._api_key)

    async def chat(self, system: str, user: str, max_tokens: int = 300) -> str:
        """调用 Chat Completions，返回模型回复文本。

        :param system: system prompt。
        :param user: user prompt。
        :param max_tokens: 最大输出 token 数。
        :returns: 模型回复文本。
        :raises RuntimeError: API Key 未配置或调用失败。
        """
        if not self.available:
            raise RuntimeError("LLM API Key 未配置（SCX_LLM_API_KEY 为空）")

        client = self._get_client()
        resp = await client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens,
            temperature=0.3,
        )
        choice = resp.choices[0]
        content = choice.message.content or ""
        finish_reason = getattr(choice, "finish_reason", None)
        if finish_reason == "length":
            logger.warning(
                "LLM 输出因 max_tokens=%d 被截断（finish_reason=length），"
                "考虑增大 max_tokens 或精简 prompt",
                max_tokens,
            )
        logger.info(
            "LLM chat ok: provider=%s model=%s tokens=%s finish=%s",
            get_settings().llm_provider,
            self.model,
            getattr(resp, "usage", None),
            finish_reason,
        )
        return content.strip()


_client: LlmClient | None = None


def get_llm_client() -> LlmClient:
    """获取全局 LLM 客户端单例。

    :returns: LlmClient 实例。
    """
    global _client
    if _client is None:
        _client = LlmClient()
    return _client
