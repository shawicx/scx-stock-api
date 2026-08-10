"""
@description AkShare 数据源实现，封装个股行情、ETF、板块、指数等能力。

内置多数据源自动切换：东方财富接口（push2.eastmoney.com）在云服务器（如阿里云 ECS）
上会被反爬封锁（RemoteDisconnected），因此在每个领域方法中配置了 fallback 链：
优先尝试字段最全的东方财富版（_em 后缀），失败后自动切换到新浪/腾讯版。
"""

import logging
from collections.abc import Callable
from typing import Any

import akshare as ak

from scx_stock.exceptions.provider import ProviderError, ProviderUnavailableError
from scx_stock.provider.base import SyncProviderBase
from scx_stock.schema.index import IndexQuote
from scx_stock.schema.kline import Kline, KlineBar
from scx_stock.schema.sector import SectorQuote
from scx_stock.schema.stock import Quote, StockInfo, StockListItem
from scx_stock.search.pinyin import make_pinyin_for_search

logger = logging.getLogger(__name__)


class AkshareProvider(SyncProviderBase):
    """AkShare 数据源 Provider。

    所有 AkShare 调用通过 _run 推入线程池执行，避免阻塞事件循环。
    每个领域方法内置 fallback：东方财富失败 → 新浪/腾讯备选。
    """

    name = "akshare"

    async def _call_with_fallback(
        self,
        sources: list[tuple[str, Callable[..., Any], dict[str, Any]]],
        domain: str,
    ) -> tuple[str, Any]:
        """按优先级尝试多个数据源函数，第一个成功就返回。

        :param sources: (数据源名, 函数, kwargs) 列表，按优先级排序。
        :param domain: 领域标识（用于日志）。
        :returns: (数据源名, 返回值) 元组，数据源名用于选择字段映射逻辑。
        :raises ProviderUnavailableError: 所有数据源均失败。
        """
        last_error: Exception | None = None
        for i, (source_name, func, kwargs) in enumerate(sources):
            try:
                result = await self._run(func, **kwargs)
                if i > 0:
                    logger.info("%s fallback to %s succeeded", domain, source_name)
                return source_name, result
            except Exception as e:  # noqa: BLE001
                logger.warning("%s source %s failed: %s", domain, source_name, e)
                last_error = e
                continue
        raise ProviderUnavailableError(
            f"{domain}: all sources failed"
        ) from last_error

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
        """获取个股实时行情（东方财富 → 新浪 → 腾讯 fallback）。

        :param code: 股票代码。
        :returns: Quote。
        :raises ProviderError: 数据源异常或代码不存在。
        """
        source, df = await self._call_with_fallback(
            [
                ("em", ak.stock_zh_a_spot_em, {}),
                ("sina", ak.stock_zh_a_spot, {}),
                ("tx", ak.stock_zh_a_spot_tx, {}),
            ],
            domain="get_quote",
        )

        if df is None or df.empty:
            raise ProviderError("quote data empty")

        if source == "tx":
            # 腾讯源代码格式为 sh600519 / sz000001
            tx_code = _to_tx_code(code)
            row = df[df["code"] == tx_code]
        else:
            row = df[df["代码"] == code]
        if row.empty:
            raise ProviderError(f"quote not found: {code}")

        r = row.iloc[0]
        if source == "tx":
            return _tx_row_to_quote(r, code)
        last = _to_float(r.get("最新价"))
        prev = _to_float(r.get("昨收"))
        change = _to_float(r.get("涨跌额"))
        if change is None and last and prev:
            change = last - prev
        change_pct = _to_float(r.get("涨跌幅"))
        if change_pct is None and change is not None and prev:
            change_pct = change / prev * 100

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

    async def get_kline(self, code: str, days: int = 120) -> Kline:
        """获取近 N 个交易日的前复权日 K 线。

        ETF 与 A 股股票使用不同 AkShare 接口：
          - ETF（代码首位 5/1）：``fund_etf_hist_em(adjust="qfq")``
          - 股票（其他）：``stock_zh_a_hist(adjust="qfq")``

        通过 ``_run`` 推入线程池执行，避免阻塞事件循环。

        :param code: 证券代码（股票或 ETF）。
        :param days: 返回的最近交易日数量。
        :returns: Kline（按日期升序）。
        :raises ProviderError: 数据源异常或代码不存在。

        :example kline = await provider.get_kline("510300", days=120)
        """
        df = await self._fetch_kline_df(code)
        if df is None or df.empty:
            raise ProviderError(f"kline data empty: {code}")

        bars: list[KlineBar] = []
        for _, r in df.iterrows():
            trade_date = _to_date(r.get("日期"))
            o = _to_float(r.get("开盘"))
            c = _to_float(r.get("收盘"))
            h = _to_float(r.get("最高"))
            low = _to_float(r.get("最低"))
            vol = _to_float(r.get("成交量"))
            if trade_date is None or c is None:
                continue
            bars.append(
                KlineBar(
                    trade_date=trade_date,
                    open=o or 0.0,
                    close=c,
                    high=h or c,
                    low=low or c,
                    volume=vol or 0.0,
                )
            )

        bars.sort(key=lambda b: b.trade_date)
        if days > 0:
            bars = bars[-days:]
        return Kline(code=code, bars=bars)

    async def _fetch_kline_df(self, code: str):
        """按代码类型选择 AkShare K 线接口拉取 DataFrame，带多源 fallback。

        ETF（代码首位 5/1）：东方财富 ``fund_etf_hist_em`` → 新浪 ``fund_etf_hist_sina``
        股票（首位 0/3/6/8）：东方财富 ``stock_zh_a_hist`` → 腾讯 ``stock_zh_a_hist_tx``

        东方财富历史接口（push2his.eastmoney.com）在部分网络环境会被反爬封锁
        （SSL 握手超时），新浪/腾讯备选保证可用性。

        :param code: 证券代码。
        :returns: 已归一化列名（中文：日期/开盘/收盘/最高/最低/成交量）的 DataFrame。
        :raises ProviderUnavailableError: 所有数据源均失败。
        """
        head = code[0] if code else ""
        is_etf = head in ("5", "1") and len(code) == 6

        if is_etf:
            sources = [
                ("em", ak.fund_etf_hist_em, {"symbol": code, "period": "daily", "adjust": "qfq"}),
                ("sina", ak.fund_etf_hist_sina, {"symbol": _to_tx_code(code)}),
            ]
        else:
            sources = [
                ("em", ak.stock_zh_a_hist, {"symbol": code, "period": "daily", "adjust": "qfq"}),
                ("tx", ak.stock_zh_a_hist_tx, {"symbol": _to_tx_code(code),
                                                "start_date": "20200101", "end_date": "20501231"}),
            ]

        source, df = await self._call_with_fallback(sources, domain=f"get_kline({code})")
        return _normalize_kline_columns(df, source)

    async def list_stocks(self) -> list[StockInfo]:
        """获取 A 股全量股票列表，用于搜索索引构建（东方财富 → 新浪 → 腾讯 fallback）。

        :returns: StockInfo 列表（含拼音与 type）。
        """
        source, df = await self._call_with_fallback(
            [
                ("em", ak.stock_zh_a_spot_em, {}),
                ("sina", ak.stock_zh_a_spot, {}),
                ("tx", ak.stock_zh_a_spot_tx, {}),
            ],
            domain="list_stocks",
        )
        if source == "tx":
            return _tx_df_to_stock_info(df, default_type="stock")
        return self._df_to_stock_info(df, default_type="stock")

    async def list_stock_quotes(
        self,
        industry_map: dict[str, str] | None = None,
    ) -> list[StockListItem]:
        """获取 A 股全市场实时行情列表（含价格/涨跌/换手/主力资金/行业）。

        数据源 fallback 链（全部走线程池，不阻塞事件循环）：
          1. 东方财富 ``stock_zh_a_spot_em``：字段全（含换手率、主力资金）
          2. 新浪 ``stock_zh_a_spot``：字段较少（无换手率），云服务器可用
          3. 腾讯 ``stock_zh_a_spot_tx``：含换手率 + 主力资金（主力净流入 zljlr）

        行业映射为增强字段，由调用方注入（来自 DB），容错失败则为 None。

        :param industry_map: code → 行业映射字典，为空则 industry 字段为 None。
        :returns: StockListItem 列表。
        :raises ProviderUnavailableError: 所有数据源不可用。
        """
        source, df = await self._call_with_fallback(
            [
                ("em", ak.stock_zh_a_spot_em, {}),
                ("sina", ak.stock_zh_a_spot, {}),
                ("tx", ak.stock_zh_a_spot_tx, {}),
            ],
            domain="list_stock_quotes",
        )

        if industry_map is None:
            industry_map = {}

        # 腾讯源自带主力资金字段（zljlr），无需额外 merge；其他源用 fund_flow_map 补充
        if source == "tx":
            return _tx_df_to_stock_quotes(df, industry_map)

        fund_flow_map = await self._fetch_fund_flow_rank()
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
        """获取全量 ETF 列表，用于搜索索引构建（东方财富 → 同花顺 fallback）。

        :returns: StockInfo 列表（含拼音与 type=etf）。
        """
        source, df = await self._call_with_fallback(
            [
                ("em", ak.fund_etf_spot_em, {}),
                ("ths", ak.fund_etf_spot_ths, {}),
            ],
            domain="list_etfs",
        )
        df = _normalize_etf_columns(df, source)
        return self._df_to_stock_info(df, default_type="etf")

    async def list_etf_quotes(self) -> list[StockListItem]:
        """获取全量 ETF 实时行情列表（东方财富 → 同花顺 fallback）。

        :returns: StockListItem 列表（market 统一为 "ETF"）。
        :raises ProviderUnavailableError: 数据源不可用。
        """
        source, df = await self._call_with_fallback(
            [
                ("em", ak.fund_etf_spot_em, {}),
                ("ths", ak.fund_etf_spot_ths, {}),
            ],
            domain="list_etf_quotes",
        )
        df = _normalize_etf_columns(df, source)

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
        """获取行业板块实时涨跌列表（东方财富 → 新浪 fallback）。

        :returns: SectorQuote 列表。
        :raises ProviderUnavailableError: 数据源不可用。
        """
        _, df = await self._call_with_fallback(
            [
                ("em", ak.stock_board_industry_name_em, {}),
                ("sina", ak.stock_sector_spot, {"indicator": "新浪行业"}),
            ],
            domain="list_sectors",
        )

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

        仅支持东方财富源（新浪接口按概念代码查询，参数语义不同）。
        主要用于 Scheduler 定时同步行业映射（本地/非高峰期，反爬风险低）。

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
        """获取指数实时行情列表（东方财富 → 新浪 fallback）。

        :param group: 指数分组（仅东方财富源使用），可选：沪深重要指数 / 上证系列指数等。
        :returns: IndexQuote 列表。
        :raises ProviderUnavailableError: 数据源不可用。
        """
        _, df = await self._call_with_fallback(
            [
                ("em", ak.stock_zh_index_spot_em, {"symbol": group}),
                ("sina", ak.stock_zh_index_spot_sina, {}),
            ],
            domain="list_indexes",
        )

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


def _to_date(v: Any):
    """安全转 date，兼容字符串与 datetime。

    :param v: 原始值。
    :returns: date 或 None。
    """
    from datetime import date, datetime

    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


# K 线列名归一化映射：各数据源列名 → 统一中文列名（与 get_kline 读取逻辑对齐）
_KLINE_COLUMN_MAP: dict[str, dict[str, str]] = {
    "em": {},  # 东方财富已是中文列名，无需映射
    "sina": {  # 新浪 fund_etf_hist_sina：date/open/high/low/close/volume
        "date": "日期",
        "open": "开盘",
        "close": "收盘",
        "high": "最高",
        "low": "最低",
        "volume": "成交量",
    },
    "tx": {  # 腾讯 stock_zh_a_hist_tx：date/open/close/high/low/volume
        "date": "日期",
        "open": "开盘",
        "close": "收盘",
        "high": "最高",
        "low": "最低",
        "volume": "成交量",
    },
}


def _normalize_kline_columns(df: Any, source: str) -> Any:
    """将不同数据源的 K 线列名归一化为统一中文列名。

    东方财富源已使用中文列名（日期/开盘/收盘/最高/最低/成交量），
    新浪/腾讯源使用英文列名（date/open/close/high/low/volume），需映射。

    :param df: AkShare 返回的 DataFrame。
    :param source: 数据源标识（em/sina/tx）。
    :returns: 列名归一化后的 DataFrame。
    """
    mapping = _KLINE_COLUMN_MAP.get(source, {})
    if not mapping or df is None or df.empty:
        return df
    return df.rename(columns=mapping)


# ETF 列名归一化映射：同花顺源列名与东方财富完全不同，需统一
_ETF_COLUMN_MAP_THS = {
    "基金代码": "代码",
    "基金名称": "名称",
    "增长率": "涨跌幅",
    "增长值": "涨跌额",
}


def _normalize_etf_columns(df: Any, source: str) -> Any:
    """将 ETF 数据源的列名归一化。

    东方财富 fund_etf_spot_em 使用中文列名（代码/名称/最新价/...），无需映射。
    同花顺 fund_etf_spot_ths 使用 基金代码/基金名称/增长率 等不同列名，需映射；
    且 THS 是净值口径，无实时价/开盘/最高/最低/成交量，这些字段留空即可。

    :param df: AkShare 返回的 DataFrame。
    :param source: 数据源标识（em/ths）。
    :returns: 列名归一化后的 DataFrame。
    """
    if source != "ths" or df is None or df.empty:
        return df
    return df.rename(columns=_ETF_COLUMN_MAP_THS)


def _classify_market(code: str) -> str:
    """按代码前缀识别市场。

    ETF（5/1 开头）也会经过此函数，在 list_etf_quotes 中会被统一覆盖为 "ETF"。

    :param code: 股票/ETF 代码。
    :returns: 市场名。
    """
    if not code:
        return "未知"
    head = code[0]
    if head in ("6", "5"):  # 沪市股票 / 沪市 ETF
        return "上证"
    if head in ("0", "3", "1"):  # 深市股票 / 深市 ETF
        return "深证"
    if head in ("8", "4"):
        return "北交所"
    return "其他"


# ---------------------------------------------------------------------------
# 腾讯财经数据源辅助映射（列名为拼音缩写，与东方财富/新浪的中文列名完全不同）
# ---------------------------------------------------------------------------


def _to_tx_code(code: str) -> str:
    """标准代码转带交易所前缀格式（sh/sz），供新浪/腾讯源使用。

    市场前缀规则：
      - 6 开头（沪市股票）→ sh
      - 5 开头（沪市 ETF/基金，如 510300）→ sh
      - 0/3 开头（深市股票）→ sz
      - 1 开头（深市 ETF/基金，如 159915）→ sz

    :param code: 标准代码，如 "600519" 或 "510300"。
    :returns: 带前缀格式，如 "sh600519" 或 "sh510300"。

    :example _to_tx_code("600519")   # "sh600519"
    :example _to_tx_code("510300")   # "sh510300"
    :example _to_tx_code("159915")   # "sz159915"
    """
    if not code:
        return code
    head = code[0]
    if head in ("6", "5"):
        return f"sh{code}"
    return f"sz{code}"


def _from_tx_code(tx_code: str) -> str:
    """腾讯格式代码转标准代码（去交易所前缀）。

    :param tx_code: 腾讯格式，如 "sh600519"。
    :returns: 标准代码，如 "600519"。
    """
    if len(tx_code) > 2 and tx_code[:2] in ("sh", "sz"):
        return tx_code[2:]
    return tx_code


def _tx_df_to_stock_quotes(
    df: Any,
    industry_map: dict[str, str] | None = None,
) -> list[StockListItem]:
    """腾讯行情 DataFrame → StockListItem 列表。

    腾讯列名映射：code→代码, name→名称, zxj→最新价, zdf→涨跌幅, zd→涨跌额,
    volume→成交量, turnover→成交额, hsl→换手率, zljlr→主力净流入（万元）。

    :param df: 腾讯 stock_zh_a_spot_tx 返回的 DataFrame。
    :param industry_map: code → 行业映射（可选）。
    :returns: StockListItem 列表。
    """
    if df is None or df.empty:
        return []

    industry_map = industry_map or {}
    out: list[StockListItem] = []

    for _, r in df.iterrows():
        tx_code = str(r.get("code", "")).strip()
        if not tx_code:
            continue
        code = _from_tx_code(tx_code)
        # 腾讯主力净流入 zljlr 单位为万元，转换为元
        inflow_wan = _to_float(r.get("zljlr"))
        inflow = inflow_wan * 1e4 if inflow_wan is not None else None
        out.append(
            StockListItem(
                code=code,
                name=str(r.get("name", "")).strip(),
                market=_classify_market(code),
                price=_to_float(r.get("zxj")),
                change=_to_float(r.get("zd")),
                change_pct=_to_float(r.get("zdf")),
                amount=_to_float(r.get("turnover")),
                volume=_to_float(r.get("volume")),
                turnover_rate=_to_float(r.get("hsl")),
                high=None,
                low=None,
                open=None,
                prev_close=None,
                main_net_inflow=inflow,
                main_net_inflow_pct=None,
                industry=industry_map.get(code),
            )
        )
    return out


def _tx_df_to_stock_info(df: Any, default_type: str) -> list[StockInfo]:
    """腾讯行情 DataFrame → StockInfo 列表（用于搜索索引构建）。

    :param df: 腾讯 stock_zh_a_spot_tx 返回的 DataFrame。
    :param default_type: stock / etf。
    :returns: StockInfo 列表。
    """
    if df is None or df.empty:
        return []

    out: list[StockInfo] = []
    for _, r in df.iterrows():
        tx_code = str(r.get("code", "")).strip()
        if not tx_code:
            continue
        code = _from_tx_code(tx_code)
        name = str(r.get("name", "")).strip()
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


def _tx_row_to_quote(r: Any, code: str) -> Quote:
    """腾讯单行 → Quote。

    :param r: 腾讯 DataFrame 的一行。
    :param code: 标准代码。
    :returns: Quote 对象。
    """
    last = _to_float(r.get("zxj"))
    change = _to_float(r.get("zd"))
    change_pct = _to_float(r.get("zdf"))
    prev = (last - change) if (last is not None and change is not None) else None
    return Quote(
        code=code,
        name=str(r.get("name", code)),
        price=last,
        prev_close=prev,
        change=change,
        change_pct=change_pct,
        volume=_to_float(r.get("volume")),
        amount=_to_float(r.get("turnover")),
        high=None,
        low=None,
        open=None,
        timestamp=_now_str(),
    )
