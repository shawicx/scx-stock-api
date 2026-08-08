"""
@description AkShare 数据源实现，封装个股行情、ETF、板块、指数等能力。
"""

import logging
from typing import Any

import akshare as ak

from scx_stock.exceptions.provider import ProviderError, ProviderUnavailableError
from scx_stock.provider.base import SyncProviderBase
from scx_stock.schema.index import IndexQuote
from scx_stock.schema.sector import SectorQuote
from scx_stock.schema.stock import Quote, StockInfo, StockListItem
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
            market=_classify_market(code),
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
        last = _to_float(r.get("最新价"))
        prev = _to_float(r.get("昨收"))
        change = last - prev if last and prev else None
        change_pct = (change / prev * 100) if (change is not None and prev) else None

        return Quote(
            code=code,
            name=str(r.get("名称", code)),
            price=last,
            prev_close=prev,
            change=change,
            change_pct=change_pct,
            volume=_to_float(r.get("成交量")),
            amount=_to_float(r.get("成交额")),
            high=_to_float(r.get("最高")),
            low=_to_float(r.get("最低")),
            open=_to_float(r.get("今开")),
            timestamp=_now_str(),
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

    async def list_stock_quotes(
        self,
        industry_map: dict[str, str] | None = None,
    ) -> list[StockListItem]:
        """获取 A 股全市场实时行情列表（含价格/涨跌/换手/主力资金/行业）。

        数据来源（全部走线程池，不阻塞事件循环）：
          - ``stock_zh_a_spot_em``：行情快照（价格/涨跌/换手等）
          - ``stock_individual_fund_flow_rank("今日")``：全市场主力资金流排名
          - ``industry_map``：由调用方注入的 code → 行业映射（来自 DB）

        :param industry_map: code → 行业映射字典，为空则 industry 字段为 None。
        :returns: StockListItem 列表。
        :raises ProviderUnavailableError: 数据源不可用。
        """
        try:
            df = await self._run(ak.stock_zh_a_spot_em)
        except Exception as e:  # noqa: BLE001
            logger.warning("akshare list_stock_quotes failed: %s", e)
            raise ProviderUnavailableError("akshare stock quote list unavailable") from e

        # 资金流排名（容错：失败则不 merge，主力资金字段为 None）
        fund_flow_map = await self._fetch_fund_flow_rank()

        # 行业映射由调用方注入（DB 来源），未注入则为空
        if industry_map is None:
            industry_map = {}

        return self._df_to_stock_quotes(df, fund_flow_map, industry_map)

    async def _fetch_fund_flow_rank(self) -> dict[str, dict[str, float]]:
        """拉取全市场主力资金流排名，返回 code → {净额, 净占比} 映射。

        容错：数据源失败时返回空字典，不阻断行情列表主链路。

        :returns: {code: {"inflow": float, "inflow_pct": float}}。
        """
        try:
            df = await self._run(ak.stock_individual_fund_flow_rank, indicator="今日")
        except Exception as e:  # noqa: BLE001
            logger.warning("akshare fund flow rank failed: %s", e)
            return {}

        if df is None or df.empty:
            return {}

        out: dict[str, dict[str, float]] = {}
        for _, r in df.iterrows():
            code = str(r.get("代码", "")).strip()
            if not code:
                continue
            out[code] = {
                "inflow": _to_float(r.get("今日主力净流入-净额")) or 0.0,
                "inflow_pct": _to_float(r.get("今日主力净流入-净占比")) or 0.0,
            }
        return out

    def _df_to_stock_quotes(
        self,
        df: Any,
        fund_flow_map: dict[str, dict[str, float]] | None = None,
        industry_map: dict[str, str] | None = None,
    ) -> list[StockListItem]:
        """把 A 股/ETF 快照 DataFrame 映射为 StockListItem 列表。

        :param df: AkShare 快照 DataFrame。
        :param fund_flow_map: code → 主力资金流映射（可选）。
        :param industry_map: code → 行业映射（可选）。
        :returns: StockListItem 列表。
        """
        if df is None or df.empty:
            return []

        fund_flow_map = fund_flow_map or {}
        industry_map = industry_map or {}

        out: list[StockListItem] = []
        for _, r in df.iterrows():
            code = str(r.get("代码", "")).strip()
            if not code:
                continue
            ff = fund_flow_map.get(code, {})
            out.append(
                StockListItem(
                    code=code,
                    name=str(r.get("名称", "")).strip(),
                    market=_classify_market(code),
                    price=_to_float(r.get("最新价")),
                    change=_to_float(r.get("涨跌额")),
                    change_pct=_to_float(r.get("涨跌幅")),
                    amount=_to_float(r.get("成交额")),
                    volume=_to_float(r.get("成交量")),
                    turnover_rate=_to_float(r.get("换手率")),
                    high=_to_float(r.get("最高")),
                    low=_to_float(r.get("最低")),
                    open=_to_float(r.get("今开")),
                    prev_close=_to_float(r.get("昨收")),
                    main_net_inflow=ff.get("inflow"),
                    main_net_inflow_pct=ff.get("inflow_pct"),
                    industry=industry_map.get(code),
                )
            )
        return out

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

    async def list_etf_quotes(self) -> list[StockListItem]:
        """获取全量 ETF 实时行情列表。

        :returns: StockListItem 列表（market 统一为 "ETF"）。
        :raises ProviderUnavailableError: 数据源不可用。
        """
        try:
            df = await self._run(ak.fund_etf_spot_em)
        except Exception as e:  # noqa: BLE001
            logger.warning("akshare list_etf_quotes failed: %s", e)
            raise ProviderUnavailableError("akshare etf quote list unavailable") from e

        items = self._df_to_stock_quotes(df)
        # ETF 不按代码前缀细分市场，统一标记
        for it in items:
            it.market = "ETF"
        return items

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
                    market=_classify_market(code),
                    pinyin=make_pinyin_for_search(name),
                    type=default_type,
                )
            )
        return out

    async def list_sectors(self) -> list[SectorQuote]:
        """获取行业板块实时涨跌列表（东方财富）。

        :returns: SectorQuote 列表。
        :raises ProviderUnavailableError: 数据源不可用。
        """
        try:
            df = await self._run(ak.stock_board_industry_name_em)
        except Exception as e:  # noqa: BLE001
            logger.warning("akshare list_sectors failed: %s", e)
            raise ProviderUnavailableError("akshare sector list unavailable") from e

        if df is None or df.empty:
            return []

        out: list[SectorQuote] = []
        for _, r in df.iterrows():
            out.append(
                SectorQuote(
                    code=str(r.get("板块代码", "")).strip(),
                    name=str(r.get("板块名称", "")).strip(),
                    price=_to_float(r.get("最新价")),
                    change=_to_float(r.get("涨跌额")),
                    change_pct=_to_float(r.get("涨跌幅")),
                    total_market_cap=_to_float(r.get("总市值")),
                    turnover_rate=_to_float(r.get("换手率")),
                    up_count=_to_int(r.get("上涨家数")),
                    down_count=_to_int(r.get("下跌家数")),
                    leading_stock=str(r.get("领涨股票") or "").strip() or None,
                    leading_stock_change_pct=_to_float(r.get("领涨股票-涨跌幅")),
                )
            )
        return out

    async def get_sector_constituents(self, sector_name: str) -> list[dict[str, str]]:
        """获取板块成分股（按板块名称，如 "小金属"）。

        :param sector_name: 板块名称（东方财富行业板块名）。
        :returns: 成分股列表，每项含 code / name。
        :raises ProviderError: 数据源异常或板块不存在。
        """
        try:
            df = await self._run(ak.stock_board_industry_cons_em, symbol=sector_name)
        except Exception as e:  # noqa: BLE001
            logger.warning("akshare get_sector_constituents failed: %s", e)
            raise ProviderUnavailableError(
                f"akshare sector constituents unavailable: {sector_name}"
            ) from e

        if df is None or df.empty:
            return []

        out: list[dict[str, str]] = []
        for _, r in df.iterrows():
            code = str(r.get("代码", "")).strip()
            if not code:
                continue
            out.append({"code": code, "name": str(r.get("名称", "")).strip()})
        return out

    async def list_indexes(self, group: str = "沪深重要指数") -> list[IndexQuote]:
        """获取指数实时行情列表（东方财富）。

        :param group: 指数分组，可选：沪深重要指数 / 上证系列指数 / 深证系列指数 /
            指数成份 / 中证系列指数。
        :returns: IndexQuote 列表。
        :raises ProviderUnavailableError: 数据源不可用。
        """
        try:
            df = await self._run(ak.stock_zh_index_spot_em, symbol=group)
        except Exception as e:  # noqa: BLE001
            logger.warning("akshare list_indexes failed: %s", e)
            raise ProviderUnavailableError("akshare index list unavailable") from e

        if df is None or df.empty:
            return []

        out: list[IndexQuote] = []
        for _, r in df.iterrows():
            out.append(
                IndexQuote(
                    code=str(r.get("代码", "")).strip(),
                    name=str(r.get("名称", "")).strip(),
                    price=_to_float(r.get("最新价")),
                    change_pct=_to_float(r.get("涨跌幅")),
                    change=_to_float(r.get("涨跌额")),
                    volume=_to_float(r.get("成交量")),
                    amount=_to_float(r.get("成交额")),
                    amplitude=_to_float(r.get("振幅")),
                    high=_to_float(r.get("最高")),
                    low=_to_float(r.get("最低")),
                    open=_to_float(r.get("今开")),
                    prev_close=_to_float(r.get("昨收")),
                )
            )
        return out


def _to_float(v: Any) -> float | None:
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


def _to_int(v: Any) -> int | None:
    """安全转 int，失败返回 None。

    :param v: 原始值。
    :returns: int 或 None。
    """
    f = _to_float(v)
    return int(f) if f is not None else None


def _now_str() -> str:
    """当前时间 ISO 字符串。

    :returns: ISO 格式时间。
    """
    from datetime import datetime

    return datetime.now().isoformat(timespec="seconds")


def _classify_market(code: str) -> str:
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
