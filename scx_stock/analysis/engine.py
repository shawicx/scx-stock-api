"""
@description 分析引擎编排层：K 线 → 指标 → 支撑/压力 → 趋势 → 结构化分析结果。

对外暴露 analyze(kline) 函数，产出不含 AI 解读的基础 AnalysisReport；
AI 解读由 llm/interpreter 独立补充，保持职责单一。
"""

import logging

from scx_stock.analysis.indicators import (
    calc_kdj,
    calc_macd,
    calc_ma,
    calc_period_change,
    calc_rsi,
    calc_volume_ratio,
    to_dataframe,
)
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
    ma20 = calc_ma(close, 20)
    ma60 = calc_ma(close, 60)
    trend_note = "" if ma60 is not None else "历史K线不足60根，趋势仅基于20日均线判断"

    # 动量与量能
    macd = calc_macd(close)
    rsi14 = calc_rsi(close)
    kdj = calc_kdj(df)
    volume_ratio = calc_volume_ratio(df)
    change_5d = calc_period_change(close, 5)
    change_20d = calc_period_change(close, 20)

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
        trend_note=trend_note,
        ma20=ma20,
        ma60=ma60,
        volume_ratio=round(volume_ratio, 2) if volume_ratio is not None else None,
        rsi14=round(rsi14, 1) if rsi14 is not None else None,
        macd_dif=round(macd[0], 4) if macd else None,
        macd_dea=round(macd[1], 4) if macd else None,
        macd_hist=round(macd[2], 4) if macd else None,
        kdj_j=round(kdj[2], 1) if kdj else None,
        change_5d=round(change_5d, 2) if change_5d is not None else None,
        change_20d=round(change_20d, 2) if change_20d is not None else None,
        summary="",  # 由 AI 解读层补充
        ok=True,
    )


def fallback_summary(report: AnalysisReport) -> str:
    """生成降级摘要（AI 不可用时使用），基于规则模板拼接。

    覆盖趋势、近期涨跌、均线位置、量能与 MACD 动量、支撑/压力位；
    趋势无法判断时如实说明，不生造"数据不足趋势"类病句。

    :param report: 分析结果。
    :returns: 自然语言摘要字符串。
    """
    if not report.ok:
        return f"分析失败：{report.error}"

    parts: list[str] = []

    # 趋势（仅拼接合法标签，避免出现"数据不足趋势"）
    if report.trend in ("多头", "空头", "震荡"):
        parts.append(f"当前处于{report.trend}趋势")
    elif report.trend:
        parts.append("当前数据不足以判断趋势")
    if report.trend_note:
        parts.append(report.trend_note)

    # 当日与近期涨跌
    if report.change_pct is not None:
        if report.change_pct > 0:
            parts.append(f"当日上涨{report.change_pct:.2f}%")
        elif report.change_pct < 0:
            parts.append(f"当日下跌{abs(report.change_pct):.2f}%")
        else:
            parts.append("当日收平")
    if report.change_5d is not None:
        parts.append(f"近5日累计{'涨' if report.change_5d >= 0 else '跌'}{abs(report.change_5d):.2f}%")
    if report.change_20d is not None:
        parts.append(f"近20日累计{'涨' if report.change_20d >= 0 else '跌'}{abs(report.change_20d):.2f}%")

    # 均线位置
    if report.close is not None and report.ma20 is not None:
        if report.close > report.ma20:
            parts.append("价格站上20日均线")
        else:
            parts.append("价格跌破20日均线")

    # 量能
    if report.volume_ratio is not None:
        if report.volume_ratio >= 1.5:
            parts.append(f"成交量明显放大（量比{report.volume_ratio}）")
        elif report.volume_ratio <= 0.7:
            parts.append(f"成交量明显萎缩（量比{report.volume_ratio}）")
        else:
            parts.append(f"量比{report.volume_ratio}，量能与近期基本相当")

    # 动量：MACD 方向 + RSI 超买超卖
    if report.macd_dif is not None and report.macd_dea is not None:
        side = "上方" if report.macd_dif > report.macd_dea else "下方"
        parts.append(f"MACD DIF 位于 DEA {side}")
    if report.rsi14 is not None:
        if report.rsi14 >= 70:
            parts.append(f"RSI(14) 为 {report.rsi14}，短期超买")
        elif report.rsi14 <= 30:
            parts.append(f"RSI(14) 为 {report.rsi14}，短期超卖")

    # 支撑 / 压力
    if report.support_1 is not None:
        parts.append(f"第一支撑位 {report.support_1.price}（{report.support_1.distance_pct}%）")
    if report.support_2 is not None:
        parts.append(f"第二支撑位 {report.support_2.price}（{report.support_2.distance_pct}%）")
    if report.resistance_1 is not None:
        parts.append(f"第一压力位 {report.resistance_1.price}（{report.resistance_1.distance_pct}%）")

    return "，".join(parts) + "。"
