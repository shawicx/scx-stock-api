"""
@description 技术指标计算，基于 pandas + pandas-ta，供支撑位分析引擎消费。

所有函数接受 pandas.DataFrame（含 close/high/low 列），返回指标标量或 Series。
"""

from typing import Any

import pandas as pd
import pandas_ta as ta


def calc_ma(close: pd.Series, period: int) -> float | None:
    """计算简单移动平均线最新值。

    :param close: 收盘价序列。
    :param period: 周期。
    :returns: 最新 MA 值；数据不足返回 None。
    """
    if len(close) < period:
        return None
    ma = ta.sma(close, length=period)
    if ma is None or ma.empty:
        return None
    val = ma.iloc[-1]
    return float(val) if pd.notna(val) else None


def calc_boll_lower(close: pd.Series) -> float | None:
    """计算布林带下轨最新值（BBANDS 20, 2）。

    :param close: 收盘价序列。
    :returns: 下轨值；数据不足返回 None。
    """
    boll = ta.bbands(close, length=20, std=2)
    if boll is None or boll.empty:
        return None
    # pandas-ta 列名：BBL_20_2.0
    lower_col = [c for c in boll.columns if c.startswith("BBL_")]
    if not lower_col:
        return None
    val = boll[lower_col[0]].iloc[-1]
    return float(val) if pd.notna(val) else None


def calc_pivot_points(high: float, low: float, close: float) -> dict[str, float]:
    """计算经典 Pivot Point 支撑/压力位。

    :param high: 前一交易日最高价。
    :param low: 前一交易日最低价。
    :param close: 前一交易日收盘价。
    :returns: 含 pivot / r1 / r2 / s1 / s2 的字典。

    :example calc_pivot_points(4.30, 4.10, 4.20)
    {"pivot": 4.20, "r1": 4.30, "r2": 4.40, "s1": 4.10, "s2": 4.00}
    """
    pivot = (high + low + close) / 3
    r1 = 2 * pivot - low
    s1 = 2 * pivot - high
    r2 = pivot + (high - low)
    s2 = pivot - (high - low)
    return {
        "pivot": round(pivot, 4),
        "r1": round(r1, 4),
        "r2": round(r2, 4),
        "s1": round(s1, 4),
        "s2": round(s2, 4),
    }


def calc_recent_low(df: pd.DataFrame, days: int) -> float | None:
    """计算近 N 日最低价。

    :param df: 含 low 列的 K 线 DataFrame。
    :param days: 回看天数。
    :returns: 最低价；数据不足返回 None。
    """
    if len(df) < days:
        days = len(df)
    if days == 0:
        return None
    low = df["low"].iloc[-days:].min()
    return float(low) if pd.notna(low) else None


def calc_recent_high(df: pd.DataFrame, days: int) -> float | None:
    """计算近 N 日最高价。

    :param df: 含 high 列的 K 线 DataFrame。
    :param days: 回看天数。
    :returns: 最高价；数据不足返回 None。
    """
    if len(df) < days:
        days = len(df)
    if days == 0:
        return None
    high = df["high"].iloc[-days:].max()
    return float(high) if pd.notna(high) else None


def to_dataframe(bars: list[Any]) -> pd.DataFrame:
    """把 KlineBar 列表转为 pandas.DataFrame，供指标计算使用。

    :param bars: KlineBar 列表（需含 trade_date/close/high/low）。
    :returns: 含 date/close/high/low/volume 列、按日期升序的 DataFrame。
    """
    if not bars:
        return pd.DataFrame(columns=["close", "high", "low", "volume"])
    rows = [
        {
            "date": b.trade_date,
            "close": b.close,
            "high": b.high,
            "low": b.low,
            "volume": b.volume,
        }
        for b in bars
    ]
    df = pd.DataFrame(rows)
    df.sort_values("date", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df
