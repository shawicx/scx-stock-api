"""
@description LLM 客户端封装，基于 OpenAI 兼容接口，支持 GLM / DeepSeek 切换。

配置优先级：DB app_setting 表 > .env（Settings）。
前端配置页面修改后下次调用即生效，无需重启。
"""

import logging

from openai import AsyncOpenAI

from scx_stock.config.dynamic import get_dynamic_settings

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

    每次调用时动态读取配置（DB 优先，.env 回退），配置变更即时生效。
    """

    async def _get_config(self) -> dict[str, str | None]:
        """从 DB + .env 读取当前生效的 LLM 配置。

        :returns: 含 provider/api_key/base_url/model/timeout 的字典。
        """
        cfg = await get_dynamic_settings(
            ["llm_provider", "llm_api_key", "llm_base_url", "llm_model", "llm_timeout"]
        )
        provider = cfg.get("llm_provider") or "deepseek"
        defaults = _PROVIDER_DEFAULTS.get(provider, {})
        return {
            "provider": provider,
            "api_key": cfg.get("llm_api_key") or "",
            "base_url": cfg.get("llm_base_url") or defaults["base_url"],
            "model": cfg.get("llm_model") or defaults["model"],
            "timeout": int(cfg.get("llm_timeout") or 30),
        }

    async def available(self) -> bool:
        """LLM 是否可用（已配置 API Key）。

        :returns: api_key 非空时为 True。
        """
        cfg = await self._get_config()
        return bool(cfg["api_key"])

    async def chat(self, system: str, user: str, max_tokens: int = 1024) -> str:
        """调用 Chat Completions，返回模型回复文本。

        :param system: system prompt。
        :param user: user prompt。
        :param max_tokens: 最大输出 token 数。
        :returns: 模型回复文本。
        :raises RuntimeError: API Key 未配置或调用失败。
        """
        cfg = await self._get_config()
        api_key = cfg["api_key"]
        if not api_key:
            raise RuntimeError("LLM API Key 未配置")

        client = AsyncOpenAI(
            api_key=api_key,
            base_url=cfg["base_url"],
            timeout=cfg["timeout"],
        )
        resp = await client.chat.completions.create(
            model=cfg["model"],
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
                "LLM 输出因 max_tokens=%d 被截断（finish_reason=length）",
                max_tokens,
            )
        logger.info(
            "LLM chat ok: provider=%s model=%s tokens=%s finish=%s",
            cfg["provider"],
            cfg["model"],
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
