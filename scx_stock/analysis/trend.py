"""
@description 趋势状态判断（规则法），基于均线排列判断多头/空头/震荡。
"""

import pandas as pd

from scx_stock.analysis.indicators import calc_ma


def judge_trend(close: pd.Series) -> str:
    """根据均线排列判断趋势状态。

    规则：
      - 收盘价 > MA20 > MA60 → 多头
      - 收盘价 < MA20 < MA60 → 空头
      - 否则 → 震荡

    :param close: 收盘价序列。
    :returns: 趋势标签：多头 / 空头 / 震荡 / 未知。
    """
    if len(close) == 0:
        return "未知"

    current = float(close.iloc[-1])
    ma20 = calc_ma(close, 20)
    ma60 = calc_ma(close, 60)

    if ma20 is None or ma60 is None:
        return "数据不足"

    if current > ma20 > ma60:
        return "多头"
    if current < ma20 < ma60:
        return "空头"
    return "震荡"
