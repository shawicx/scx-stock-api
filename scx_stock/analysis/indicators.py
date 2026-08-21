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


def calc_macd(close: pd.Series) -> tuple[float, float, float] | None:
    """计算 MACD 最新值（12, 26, 9）。

    :param close: 收盘价序列。
    :returns: (DIF, DEA, 柱状值) 元组；数据不足返回 None。

    :example calc_macd(close)
    (0.05, 0.03, 0.02)
    """
    macd = ta.macd(close, fast=12, slow=26, signal=9)
    if macd is None or macd.empty:
        return None
    cols = {c.split("_")[0]: c for c in macd.columns}
    dif_col = cols.get("MACD")
    dea_col = cols.get("MACDs")
    hist_col = cols.get("MACDh")
    if not dif_col or not dea_col or not hist_col:
        return None
    dif, dea, hist = (macd[c].iloc[-1] for c in (dif_col, dea_col, hist_col))
    if any(pd.isna(v) for v in (dif, dea, hist)):
        return None
    return float(dif), float(dea), float(hist)


def calc_rsi(close: pd.Series, period: int = 14) -> float | None:
    """计算 RSI 最新值。

    :param close: 收盘价序列。
    :param period: RSI 周期，默认 14。
    :returns: 最新 RSI 值（0~100）；数据不足返回 None。
    """
    rsi = ta.rsi(close, length=period)
    if rsi is None or rsi.empty:
        return None
    val = rsi.iloc[-1]
    return float(val) if pd.notna(val) else None


def calc_kdj(df: pd.DataFrame) -> tuple[float, float, float] | None:
    """计算 KDJ 最新值（9, 3, 3）。

    :param df: 含 high/low/close 列的 K 线 DataFrame。
    :returns: (K, D, J) 元组；数据不足返回 None。

    :example calc_kdj(df)
    (78.5, 70.2, 95.1)
    """
    kdj = ta.kdj(df["high"], df["low"], df["close"], length=9, signal=3)
    if kdj is None or kdj.empty:
        return None
    cols = {c.split("_")[0]: c for c in kdj.columns}
    k_col = cols.get("K")
    d_col = cols.get("D")
    j_col = cols.get("J")
    if not k_col or not d_col or not j_col:
        return None
    k, d, j = (kdj[c].iloc[-1] for c in (k_col, d_col, j_col))
    if any(pd.isna(v) for v in (k, d, j)):
        return None
    return float(k), float(d), float(j)


def calc_volume_ratio(df: pd.DataFrame, period: int = 5) -> float | None:
    """计算量比：最新一根 K 线成交量 / 前(period) 根 K 线平均成交量。

    :param df: 含 volume 列的 K 线 DataFrame。
    :param period: 均量回看周期，默认 5。
    :returns: 量比；数据不足（含零均量）返回 None。
    """
    vol = df["volume"]
    if len(vol) < period + 1:
        return None
    base = float(vol.iloc[-(period + 1) : -1].mean())
    if base <= 0 or pd.isna(base):
        return None
    return float(vol.iloc[-1]) / base


def calc_period_change(close: pd.Series, days: int) -> float | None:
    """计算近 N 日涨跌幅（%）。

    :param close: 收盘价序列。
    :param days: 回看天数。
    :returns: (最新收盘 - N 日前收盘) / N 日前收盘 * 100；数据不足返回 None。
    """
    if len(close) < days + 1:
        return None
    latest = float(close.iloc[-1])
    past = float(close.iloc[-(days + 1)])
    if past <= 0 or pd.isna(past):
        return None
    return (latest - past) / past * 100


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
