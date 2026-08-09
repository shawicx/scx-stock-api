"""
@description 支撑位/压力位筛选引擎：收集候选 → 过滤 → 聚类 → 排序 → 输出。

核心逻辑：
1. 从技术指标收集候选价位（MA、BOLL、Pivot、前低/前高）
2. 支撑位只保留 < 当前收盘价的候选，压力位只保留 > 收盘价的候选
3. 相近价位按容差聚类合并，记录命中来源
4. 按距离当前价从近到远排序，取前若干个
"""

import pandas as pd

from scx_stock.analysis.indicators import (
    calc_boll_lower,
    calc_ma,
    calc_pivot_points,
    calc_recent_high,
    calc_recent_low,
)
from scx_stock.schema.analysis import SupportLevel

# 聚类容差：价位相差 1% 以内视为同一支撑/压力簇
_CLUSTER_TOLERANCE = 0.01


def _collect_candidates(
    df: pd.DataFrame, current_price: float
) -> list[tuple[float, str]]:
    """收集所有候选价位及其来源标签。

    :param df: K 线 DataFrame（含 close/high/low）。
    :param current_price: 当前收盘价。
    :returns: (价位, 来源标签) 列表。
    """
    close = df["close"]
    candidates: list[tuple[float, str]] = []

    # 均线
    for period in (20, 60, 120):
        ma = calc_ma(close, period)
        if ma is not None:
            candidates.append((ma, f"MA{period}"))

    # 布林带下轨
    boll_low = calc_boll_lower(close)
    if boll_low is not None:
        candidates.append((boll_low, "BOLL下轨"))

    # Pivot Point（取前一交易日数据）
    if len(df) >= 2:
        prev = df.iloc[-2]
        pivot = calc_pivot_points(prev["high"], prev["low"], prev["close"])
        candidates.append((pivot["s1"], "Pivot S1"))
        candidates.append((pivot["s2"], "Pivot S2"))
        candidates.append((pivot["r1"], "Pivot R1"))
        candidates.append((pivot["r2"], "Pivot R2"))

    # 近期低点
    for days in (20, 60):
        low = calc_recent_low(df, days)
        if low is not None:
            candidates.append((low, f"{days}日低点"))

    # 近期高点
    for days in (20, 60):
        high = calc_recent_high(df, days)
        if high is not None:
            candidates.append((high, f"{days}日高点"))

    return candidates


def _cluster(
    prices_with_source: list[tuple[float, str]],
    current_price: float,
    is_support: bool,
) -> list[tuple[float, list[str]]]:
    """对候选价位聚类合并。

    :param prices_with_source: (价位, 来源) 列表。
    :param current_price: 当前收盘价。
    :param is_support: True 只保留 < 收盘价的候选，False 只保留 > 收盘价的。
    :returns: (聚类中心价, 来源列表) 列表，按距离当前价从近到远排序。
    """
    # 过滤方向
    if is_support:
        filtered = [(p, s) for p, s in prices_with_source if p < current_price]
        filtered.sort(key=lambda x: current_price - x[0])  # 距离从近到远
    else:
        filtered = [(p, s) for p, s in prices_with_source if p > current_price]
        filtered.sort(key=lambda x: x[0] - current_price)

    if not filtered:
        return []

    # 聚类：相邻价位差在容差内合并
    clusters: list[tuple[float, list[str]]] = []
    for price, source in filtered:
        merged = False
        for i, (center, sources) in enumerate(clusters):
            if abs(price - center) / center <= _CLUSTER_TOLERANCE:
                # 合并到已有簇：更新为簇内均价，追加来源
                sources.append(source)
                clusters[i] = (
                    round(sum([c for c, _ in [(center, None)] + [(price, None)]]) / 2, 4),
                    sources,
                )
                merged = True
                break
        if not merged:
            clusters.append((round(price, 4), [source]))

    return clusters


def _strength_label(source_count: int) -> str:
    """按命中来源数打强度标签。

    :param source_count: 命中来源数量。
    :returns: 强 / 中 / 弱。
    """
    if source_count >= 3:
        return "强"
    if source_count == 2:
        return "中"
    return "弱"


def find_supports(
    df: pd.DataFrame, current_price: float, top_n: int = 2
) -> list[SupportLevel]:
    """筛选支撑位。

    :param df: K 线 DataFrame。
    :param current_price: 当前收盘价。
    :param top_n: 返回的支撑位数量。
    :returns: SupportLevel 列表（按距离从近到远）。
    """
    candidates = _collect_candidates(df, current_price)
    clusters = _cluster(candidates, current_price, is_support=True)

    levels: list[SupportLevel] = []
    for price, sources in clusters[:top_n]:
        levels.append(
            SupportLevel(
                price=price,
                sources=sources,
                distance_pct=round((price - current_price) / current_price * 100, 2),
                strength=_strength_label(len(sources)),
            )
        )
    return levels


def find_resistances(
    df: pd.DataFrame, current_price: float, top_n: int = 1
) -> list[SupportLevel]:
    """筛选压力位。

    :param df: K 线 DataFrame。
    :param current_price: 当前收盘价。
    :param top_n: 返回的压力位数量。
    :returns: SupportLevel 列表（按距离从近到远）。
    """
    candidates = _collect_candidates(df, current_price)
    clusters = _cluster(candidates, current_price, is_support=False)

    levels: list[SupportLevel] = []
    for price, sources in clusters[:top_n]:
        levels.append(
            SupportLevel(
                price=price,
                sources=sources,
                distance_pct=round((price - current_price) / current_price * 100, 2),
                strength=_strength_label(len(sources)),
            )
        )
    return levels
