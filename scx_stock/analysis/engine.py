"""
@description 分析引擎编排层：K 线 → 指标 → 支撑/压力 → 趋势 → 结构化分析结果。

对外暴露 analyze(kline) 函数，产出不含 AI 解读的基础 AnalysisReport；
AI 解读由 llm/interpreter 独立补充，保持职责单一。
"""

import logging

from scx_stock.analysis.indicators import calc_ma, to_dataframe
from scx_stock.analysis.support import find_resistances, find_supports
from scx_stock.analysis.trend import judge_trend
from scx_stock.schema.analysis import AnalysisReport
from scx_stock.schema.kline import Kline

logger = logging.getLogger(__name__)


def analyze(kline: Kline) -> AnalysisReport:
    """对单只标的的 K 线执行支撑位/压力位/趋势分析。

    :param kline: 前复权日 K 线数据。
    :returns: AnalysisReport（summary 字段留空，由 AI 解读层补充）。
    """
    code = kline.code
    bars = kline.bars

    if len(bars) < 30:
        return AnalysisReport(
            code=code,
            name=kline.name,
            ok=False,
            error=f"K 线数据不足（仅 {len(bars)} 根，需至少 30 根）",
        )

    df = to_dataframe(bars)
    close = df["close"]
    current_price = float(close.iloc[-1])
    last_bar = bars[-1]

    # 涨跌幅
    if len(bars) >= 2:
        prev_close = bars[-2].close
        change_pct = round((current_price - prev_close) / prev_close * 100, 2)
    else:
        change_pct = None

    # 支撑 / 压力
    supports = find_supports(df, current_price, top_n=2)
    resistances = find_resistances(df, current_price, top_n=1)

    # 趋势
    trend = judge_trend(close)

    return AnalysisReport(
        code=code,
        name=kline.name,
        trade_date=last_bar.trade_date,
        close=round(current_price, 4),
        change_pct=change_pct,
        support_1=supports[0] if len(supports) >= 1 else None,
        support_2=supports[1] if len(supports) >= 2 else None,
        resistance_1=resistances[0] if len(resistances) >= 1 else None,
        trend=trend,
        ma20=calc_ma(close, 20),
        ma60=calc_ma(close, 60),
        summary="",  # 由 AI 解读层补充
        ok=True,
    )


def fallback_summary(report: AnalysisReport) -> str:
    """生成降级摘要（AI 不可用时使用），基于规则模板拼接。

    :param report: 分析结果。
    :returns: 自然语言摘要字符串。
    """
    if not report.ok:
        return f"分析失败：{report.error}"

    parts: list[str] = []
    parts.append(f"当前处于{report.trend}趋势")

    if report.close is not None and report.ma20 is not None:
        if report.close > report.ma20:
            parts.append("价格站上20日均线")
        else:
            parts.append("价格跌破20日均线")

    if report.support_1 is not None:
        parts.append(f"第一支撑位 {report.support_1.price}")
    if report.support_2 is not None:
        parts.append(f"第二支撑位 {report.support_2.price}")
    if report.resistance_1 is not None:
        parts.append(f"第一压力位 {report.resistance_1.price}")

    return "，".join(parts) + "。"
