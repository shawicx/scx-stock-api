"""
@description AkShare 数据源实现，封装个股行情、ETF、搜索等能力。
"""

import logging
from typing import Any

import akshare as ak

from scx_stock.exceptions.provider import ProviderError, ProviderUnavailableError
from scx_stock.provider.base import SyncProviderBase
from scx_stock.schema.stock import Quote, StockInfo
from scx_stock.search.pinyin import make_pinyin_for_search

logger = logging.getLogger(__name__)


class AkshareProvider(SyncProviderBase):
    """AkShare 数据源 Provider。

    所有 AkShare 调用通过 _run 推入线程池执行，避免阻塞事件循环。
    """

    name = "akshare"

    async def get_stock(self, code: str) -> StockInfo:
        """获取个股基础信息（由实时行情派生）。

        :param code: 股票代码。
        :returns: StockInfo。
        :raises ProviderError: 数据源异常或代码不存在。
        """
        try:
            df = await self._run(ak.stock_individual_info_em, symbol=code)
        except Exception as e:  # noqa: BLE001
            logger.warning("akshare get_stock failed: %s", e)
            raise ProviderUnavailableError(f"akshare stock info unavailable: {code}") from e

        if df is None or df.empty:
            raise ProviderError(f"stock not found: {code}")

        info: dict[str, str] = {}
        # akshare 返回两列：item / value
        for _, row in df.iterrows():
            info[str(row.iloc[0])] = str(row.iloc[1])

        return StockInfo(
            code=code,
            name=info.get("股票简称", code),
            market=__classify_market(code),
            industry=info.get("行业"),
        )

    async def get_quote(self, code: str) -> Quote:
        """获取个股实时行情。

        :param code: 股票代码。
        :returns: Quote。
        :raises ProviderError: 数据源异常或代码不存在。
        """
        try:
            df = await self._run(ak.stock_zh_a_spot_em)  # 全市场快照
        except Exception as e:  # noqa: BLE001
            logger.warning("akshare get_quote failed: %s", e)
            raise ProviderUnavailableError("akshare quote unavailable") from e

        if df is None or df.empty:
            raise ProviderError("quote data empty")

        row = df[df["代码"] == code]
        if row.empty:
            raise ProviderError(f"quote not found: {code}")

        r = row.iloc[0]
        last = __to_float(r.get("最新价"))
        prev = __to_float(r.get("昨收"))
        change = last - prev if last and prev else None
        change_pct = (change / prev * 100) if (change is not None and prev) else None

        return Quote(
            code=code,
            name=str(r.get("名称", code)),
            price=last,
            prev_close=prev,
            change=change,
            change_pct=change_pct,
            volume=__to_float(r.get("成交量")),
            amount=__to_float(r.get("成交额")),
            high=__to_float(r.get("最高")),
            low=__to_float(r.get("最低")),
            open=__to_float(r.get("今开")),
            timestamp=__now_str(),
        )

    async def list_stocks(self) -> list[StockInfo]:
        """获取 A 股全量股票列表，用于搜索索引构建。

        :returns: StockInfo 列表（含拼音与 type）。
        """
        try:
            df = await self._run(ak.stock_zh_a_spot_em)
        except Exception as e:  # noqa: BLE001
            logger.warning("akshare list_stocks failed: %s", e)
            raise ProviderUnavailableError("akshare stock list unavailable") from e

        return self._df_to_stock_info(df, default_type="stock")

    async def list_etfs(self) -> list[StockInfo]:
        """获取全量 ETF 列表，用于搜索索引构建。

        :returns: StockInfo 列表（含拼音与 type=etf）。
        """
        try:
            df = await self._run(ak.fund_etf_spot_em)
        except Exception as e:  # noqa: BLE001
            logger.warning("akshare list_etfs failed: %s", e)
            raise ProviderUnavailableError("akshare etf list unavailable") from e

        return self._df_to_stock_info(df, default_type="etf")

    def _df_to_stock_info(self, df: Any, default_type: str) -> list[StockInfo]:
        """把 AkShare DataFrame 转为 StockInfo 列表。

        :param df: AkShare 返回的 DataFrame。
        :param default_type: 默认类型（stock/etf）。
        :returns: StockInfo 列表。
        """
        if df is None or df.empty:
            return []

        out: list[StockInfo] = []
        for _, r in df.iterrows():
            code = str(r.get("代码", "")).strip()
            if not code:
                continue
            name = str(r.get("名称", "")).strip()
            out.append(
                StockInfo(
                    code=code,
                    name=name,
                    market=__classify_market(code),
                    pinyin=make_pinyin_for_search(name),
                    type=default_type,
                )
            )
        return out


def __to_float(v: Any) -> float | None:
    """安全转 float，失败返回 None。

    :param v: 原始值。
    :returns: float 或 None。
    """
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def __now_str() -> str:
    """当前时间 ISO 字符串。

    :returns: ISO 格式时间。
    """
    from datetime import datetime

    return datetime.now().isoformat(timespec="seconds")


def __classify_market(code: str) -> str:
    """按代码前缀识别市场。

    :param code: 股票代码。
    :returns: 市场名。
    """
    if not code:
        return "未知"
    head = code[0]
    if head == "6":
        return "上证"
    if head in ("0", "3"):
        return "深证"
    if head in ("8", "4"):
        return "北交所"
    return "其他"
