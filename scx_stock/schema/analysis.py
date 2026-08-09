"""
@description 支撑位分析结果数据模型，供分析引擎产出与 AI 解读、邮件渲染消费。
"""

from datetime import date

from pydantic import BaseModel, Field


class SupportLevel(BaseModel):
    """单个支撑/压力位。

    :param price: 价位。
    :param sources: 命中来源列表（如 MA20、BOLL下轨、20日低点）。
    :param distance_pct: 距离当前价的百分比（支撑为负，压力为正）。
    :param strength: 强度标签：强 / 中 / 弱。
    """

    price: float
    sources: list[str] = Field(default_factory=list)
    distance_pct: float
    strength: str = "中"


class AnalysisReport(BaseModel):
    """单只标的的完整分析结果。

    :param code: 证券代码。
    :param name: 简称。
    :param trade_date: 分析依据的最新交易日。
    :param close: 最新收盘价。
    :param change_pct: 当日涨跌幅（%）。
    :param support_1: 第一支撑位（最近的支撑）。
    :param support_2: 第二支撑位（次近的支撑）。
    :param resistance_1: 第一压力位（最近的压力）。
    :param trend: 趋势状态：多头 / 空头 / 震荡。
    :param ma20: MA20 值。
    :param ma60: MA60 值。
    :param summary: AI 解读摘要（或降级模板文字）。
    :param ok: 分析是否成功。
    :param error: 失败原因（ok=False 时填写）。
    """

    code: str
    name: str = ""
    trade_date: date | None = None
    close: float | None = None
    change_pct: float | None = None
    support_1: SupportLevel | None = None
    support_2: SupportLevel | None = None
    resistance_1: SupportLevel | None = None
    trend: str = ""
    ma20: float | None = None
    ma60: float | None = None
    summary: str = ""
    ok: bool = True
    error: str = ""
