"""
@description AI 解读层：把分析引擎产出的结构化结果喂给 LLM，生成自然语言摘要。

强调：LLM 只做"翻译"，不得编造数值。失败时降级为规则模板拼接（engine.fallback_summary）。
"""

import logging

from scx_stock.analysis.engine import fallback_summary
from scx_stock.llm.client import get_llm_client
from scx_stock.schema.analysis import AnalysisReport

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "你是一名严谨的 ETF/股票技术分析师。根据程序计算出的结构化技术分析结果，"
    "用简洁的中文生成一段（100~200字）投资观察摘要。\n"
    "严格要求：\n"
    "1. 只能使用输入中给出的数值，严禁编造或修改任何价格、百分比、指标值。\n"
    "2. 内容包括：当前趋势、关键支撑位与压力位、明日关注点。\n"
    "3. 末尾加一句简短免责：以上为技术分析参考，不构成投资建议。\n"
    "4. 不要使用 Markdown 标题，输出纯文本段落，务必完整不要截断。"
)


def _build_user_prompt(report: AnalysisReport) -> str:
    """根据结构化分析结果构造 LLM user prompt。

    :param report: 分析结果。
    :returns: 自然语言描述的输入数据。
    """
    lines = [
        f"标的：{report.name}（{report.code}）",
        f"日期：{report.trade_date}",
        f"收盘价：{report.close}",
        f"当日涨跌幅：{report.change_pct}%",
        f"趋势状态：{report.trend}",
        f"MA20：{report.ma20}",
        f"MA60：{report.ma60}",
    ]

    if report.support_1:
        lines.append(
            f"第一支撑位：{report.support_1.price}"
            f"（距当前价 {report.support_1.distance_pct}%，"
            f"来源：{'/'.join(report.support_1.sources)}，强度：{report.support_1.strength}）"
        )
    if report.support_2:
        lines.append(
            f"第二支撑位：{report.support_2.price}"
            f"（距当前价 {report.support_2.distance_pct}%，"
            f"来源：{'/'.join(report.support_2.sources)}）"
        )
    if report.resistance_1:
        lines.append(
            f"第一压力位：{report.resistance_1.price}"
            f"（距当前价 {report.resistance_1.distance_pct}%，"
            f"来源：{'/'.join(report.resistance_1.sources)}）"
        )

    return "\n".join(lines)


async def interpret(report: AnalysisReport) -> AnalysisReport:
    """对分析结果生成 AI 摘要，回填 report.summary。

    LLM 不可用或调用失败时降级为规则模板拼接，不抛异常。

    :param report: 分析引擎产出的结构化结果（summary 应为空）。
    :returns: 同一 report 对象，summary 字段已填充。
    """
    if not report.ok:
        report.summary = fallback_summary(report)
        return report

    client = get_llm_client()
    if not client.available:
        logger.info("LLM 未配置，使用降级模板摘要")
        report.summary = fallback_summary(report)
        return report

    try:
        user_prompt = _build_user_prompt(report)
        summary = await client.chat(
            system=_SYSTEM_PROMPT,
            user=user_prompt,
            max_tokens=1024,
        )
        # LLM 偶发返回空内容（content=None / 空字符串），此时降级为模板摘要
        report.summary = summary if summary else fallback_summary(report)
    except Exception as e:  # noqa: BLE001
        logger.warning("LLM 解读失败，降级为模板摘要: %s", e)
        report.summary = fallback_summary(report)

    return report
