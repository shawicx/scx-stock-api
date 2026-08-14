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
from scx_stock.schema.gold import GoldQuote
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
        validate: Callable[[Any], bool] | None = None,
    ) -> tuple[str, Any]:
        """按优先级尝试多个数据源函数，第一个成功就返回。

        :param sources: (数据源名, 函数, kwargs) 列表，按优先级排序。
        :param domain: 领域标识（用于日志）。
        :param validate: 可选的结果有效性校验回调。返回 False 时视为失败继续 fallback。
                         用于处理"拉到空 DataFrame / 列名不匹配"等静默失败场景。
        :returns: (数据源名, 返回值) 元组，数据源名用于选择字段映射逻辑。
        :raises ProviderUnavailableError: 所有数据源均失败。
        """
        last_error: Exception | None = None
        for i, (source_name, func, kwargs) in enumerate(sources):
            try:
                result = await self._run(func, **kwargs)
                # 结果有效性校验：不通过则视为失败继续 fallback
                if validate is not None and not validate(result):
                    logger.warning(
                        "%s source %s returned invalid result, trying next",
                        domain, source_name,
                    )
                    continue
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
            validate=_validate_df_with_columns("代码", "code"),
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

        source, df = await self._call_with_fallback(
            sources,
            domain=f"get_kline({code})",
            validate=_validate_df_with_columns("日期", "date"),
        )
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
            validate=_validate_df_with_columns("代码", "code"),
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
            validate=_validate_df_with_columns("代码", "code"),
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
        """获取全量 ETF 列表，用于搜索索引构建（新浪 → 新浪json_v2 → 东方财富 → 同花顺 fallback）。

        数据源优先级说明：新浪单次请求 ~1 秒返回全量（1600+）；
        新浪 json_v2 分页接口对数据中心 IP 友好（ECS 上 jsonp 版被反爬时可用它兜底）；
        东方财富需分页拉取 15 页且在 ECS 上被反爬封锁，同花顺经常超时。

        :returns: StockInfo 列表（含拼音与 type=etf）。
        """
        source, df = await self._call_with_fallback(
            [
                ("sina", ak.fund_etf_category_sina, {"symbol": "ETF基金"}),
                ("sina_v2", _fetch_etf_list_sina_v2, {}),
                ("em", ak.fund_etf_spot_em, {}),
                ("ths", ak.fund_etf_spot_ths, {}),
            ],
            domain="list_etfs",
            validate=_validate_df_with_columns("代码", "基金代码"),
        )
        df = _normalize_etf_columns(df, source)
        return self._df_to_stock_info(df, default_type="etf")

    async def list_etf_quotes(self) -> list[StockListItem]:
        """获取全量 ETF 实时行情列表（新浪 → 新浪json_v2 → 东方财富 → 同花顺 fallback）。

        数据源优先级同 list_etfs：新浪最快（~1s），json_v2 版对数据中心
        IP 友好，东方财富在 ECS 上被反爬封锁，同花顺经常超时。

        :returns: StockListItem 列表（market 统一为 "ETF"）。
        :raises ProviderUnavailableError: 数据源不可用。
        """
        source, df = await self._call_with_fallback(
            [
                ("sina", ak.fund_etf_category_sina, {"symbol": "ETF基金"}),
                ("sina_v2", _fetch_etf_list_sina_v2, {}),
                ("em", ak.fund_etf_spot_em, {}),
                ("ths", ak.fund_etf_spot_ths, {}),
            ],
            domain="list_etf_quotes",
            validate=_validate_df_with_columns("代码", "基金代码"),
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
        """获取行业板块实时涨跌列表（新浪 → 东方财富 fallback）。

        :returns: SectorQuote 列表。
        :raises ProviderUnavailableError: 数据源不可用。
        """
        source, df = await self._call_with_fallback(
            [
                ("sina", ak.stock_sector_spot, {"indicator": "新浪行业"}),
                ("em", ak.stock_board_industry_name_em, {}),
            ],
            domain="list_sectors",
            validate=_validate_df_with_columns("板块", "板块名称"),
        )

        if df is None or df.empty:
            return []

        out: list[SectorQuote] = []
        for _, r in df.iterrows():
            if source == "sina":
                out.append(
                    SectorQuote(
                        code=str(r.get("label", "")).strip(),
                        name=str(r.get("板块", "")).strip(),
                        label=str(r.get("label", "")).strip(),
                        price=_to_float(r.get("平均价格")),
                        change=_to_float(r.get("涨跌额")),
                        change_pct=_to_float(r.get("涨跌幅")),
                        up_count=_to_int(r.get("公司家数")),
                        leading_stock=str(r.get("股票名称") or "").strip() or None,
                    )
                )
            else:
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

    async def get_sector_constituents(
        self, sector_name: str, sector_label: str = ""
    ) -> list[dict[str, str]]:
        """获取板块成分股（新浪 → 东方财富 fallback）。

        新浪按 label 查询（如 "new_xjsc"），东方财富按板块名称查询（如 "小金属"）。
        新浪优先，失败后用东方财富（需调用方提供 sector_name）。

        :param sector_name: 板块名称（东方财富行业板块名，用于 fallback）。
        :param sector_label: 新浪板块 label（优先使用）。
        :returns: 成分股列表，每项含 code / name。
        """
        # 构造 fallback 链
        sources: list[tuple[str, Callable[..., Any], dict[str, Any]]] = []
        if sector_label:
            sources.append(
                ("sina", ak.stock_sector_detail, {"sector": sector_label})
            )
        sources.append(
            ("em", ak.stock_board_industry_cons_em, {"symbol": sector_name}),
        )

        try:
            source, df = await self._call_with_fallback(
                sources,
                domain=f"get_sector_constituents({sector_name})",
                validate=lambda d: d is not None and not d.empty,
            )
        except ProviderUnavailableError:
            return []

        if source == "sina":
            # 新浪源列名：symbol / code / name
            out: list[dict[str, str]] = []
            for _, r in df.iterrows():
                code = str(r.get("code", "")).strip()
                if not code:
                    continue
                out.append({"code": code, "name": str(r.get("name", "")).strip()})
            return out

        # 东方财富源列名：代码 / 名称
        out2: list[dict[str, str]] = []
        for _, r in df.iterrows():
            code = str(r.get("代码", "")).strip()
            if not code:
                continue
            out2.append({"code": code, "name": str(r.get("名称", "")).strip()})
        return out2

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
            validate=_validate_df_with_columns("代码", "code"),
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

    async def list_gold_quotes(self) -> list[GoldQuote]:
        """获取国内黄金品种实时行情（沪金主连 + 上金所现货 + 纽约金跟踪）。

        三个品种独立容错，单个失败不影响其他：
          - AU0（沪金主连）：``futures_zh_realtime(symbol='黄金')`` 过滤 symbol=AU0
          - Au99.99（上金所现货）：``spot_quotations_sge()`` 取最新分时
          - NYAuTN06（纽约金跟踪）：``spot_hist_sge(symbol='NYAuTN06')`` 取最后一行

        注意：期货接口的 changepercent 返回小数（0.015 表示 1.5%），需 ×100。

        :returns: GoldQuote 列表（最多 3 个品种）。
        """
        results: list[GoldQuote] = []

        # 1. 沪金主连 AU0
        au0 = await self._fetch_au0_quote()
        if au0:
            results.append(au0)

        # 2. 上金所现货 Au99.99
        sge = await self._fetch_sge_spot_quote("Au99.99", "上金所Au99.99")
        if sge:
            results.append(sge)

        # 3. 纽约金跟踪 NYAuTN06
        ny = await self._fetch_sge_hist_quote("NYAuTN06", "纽约金TN06")
        if ny:
            results.append(ny)

        return results

    async def _fetch_au0_quote(self) -> GoldQuote | None:
        """获取沪金主连 AU0 实时盘口。

        :returns: GoldQuote 或 None（失败时容错返回 None）。
        """
        try:
            df = await self._run(ak.futures_zh_realtime, symbol="黄金")
        except Exception as e:  # noqa: BLE001
            logger.warning("获取沪金期货行情失败: %s", e)
            return None

        if df is None or df.empty:
            return None

        row = df[df["symbol"] == "AU0"]
        if row.empty:
            return None
        r = row.iloc[0]
        price = _to_float(r.get("trade"))
        prev_close = _to_float(r.get("preclose"))
        change = _to_float(r.get("trade", 0)) - (prev_close or 0) if price and prev_close else None
        # changepercent 返回小数，需 ×100 转为百分数
        change_pct_raw = _to_float(r.get("changepercent"))
        change_pct = change_pct_raw * 100 if change_pct_raw is not None else None

        return GoldQuote(
            code="AU0",
            name="沪金主连",
            category="futures_shfe",
            price=price,
            change=change,
            change_pct=change_pct,
            prev_close=prev_close,
            prev_settlement=_to_float(r.get("prevsettlement")),
            open=_to_float(r.get("open")),
            high=_to_float(r.get("high")),
            low=_to_float(r.get("low")),
            volume=_to_float(r.get("volume")),
            position=_to_float(r.get("position")),
            timestamp=f"{r.get('tradedate', '')} {r.get('ticktime', '')}".strip(),
        )

    async def _fetch_sge_spot_quote(
        self, symbol: str, name: str
    ) -> GoldQuote | None:
        """获取上金所现货品种实时分时最新数据。

        spot_quotations_sge 返回列：品种/时间/现价/更新时间

        :param symbol: 品种代码（如 Au99.99）。
        :param name: 展示名称。
        :returns: GoldQuote 或 None。
        """
        try:
            df = await self._run(ak.spot_quotations_sge)
        except Exception as e:  # noqa: BLE001
            logger.warning("获取上金所现货行情失败: %s", e)
            return None

        if df is None or df.empty:
            return None

        # 该接口返回全品种分时，需过滤目标品种
        if "品种" in df.columns:
            df = df[df["品种"] == symbol]
        if df.empty:
            return None

        r = df.iloc[-1]  # 最新一根分时
        price = _to_float(r.get("现价"))
        update_time = str(r.get("更新时间", ""))

        return GoldQuote(
            code=symbol,
            name=name,
            category="spot_sge",
            price=price,
            change=None,
            change_pct=None,
            prev_close=None,
            open=None,
            high=None,
            low=None,
            volume=None,
            position=None,
            timestamp=update_time,
        )

    async def _fetch_sge_hist_quote(
        self, symbol: str, name: str
    ) -> GoldQuote | None:
        """获取上金所品种历史日 K 的最新一行（用于 NYAuTN06 等无实时接口的品种）。

        :param symbol: 品种代码（如 NYAuTN06）。
        :param name: 展示名称。
        :returns: GoldQuote 或 None。
        """
        try:
            df = await self._run(ak.spot_hist_sge, symbol=symbol)
        except Exception as e:  # noqa: BLE001
            logger.warning("获取上金所历史行情失败 %s: %s", symbol, e)
            return None

        if df is None or df.empty:
            return None

        r = df.iloc[-1]  # 最新一行
        price = _to_float(r.get("close"))
        open = _to_float(r.get("open"))

        return GoldQuote(
            code=symbol,
            name=name,
            category="comex_proxy",
            price=price,
            change=None,
            change_pct=None,
            prev_close=None,
            prev_settlement=None,
            open=open,
            high=_to_float(r.get("high")),
            low=_to_float(r.get("low")),
            volume=None,
            position=None,
            timestamp=str(r.get("date", "")),
        )


def _validate_non_empty_df(df: Any) -> bool:
    """通用 DataFrame 有效性校验：非 None、非空。

    用于 _call_with_fallback 的 validate 回调，防御"拉到空 DataFrame"
    的静默失败场景（如 ETF 同步 bug 的根因）。

    :param df: 待校验的 DataFrame。
    :returns: 有效返回 True。
    """
    return df is not None and hasattr(df, "empty") and not df.empty


def _validate_df_with_columns(*required_cols: str) -> Callable[[Any], bool]:
    """构造一个校验函数，要求 DataFrame 非空且包含至少一个候选列名。

    不同数据源的列名可能不同（如东方财富"代码"vs 腾讯"code"），
    传入多组候选列名，只要 DataFrame 含任一候选即通过。

    :param required_cols: 候选列名列表。
    :returns: 校验函数。
    """
    def _check(df: Any) -> bool:
        if not _validate_non_empty_df(df):
            return False
        columns = set(str(c) for c in df.columns)
        return any(col in columns for col in required_cols)
    return _check


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

# 新浪 json_v2 ETF 接口原始字段 → 归一化中文列名
_ETF_SINA_V2_COLUMN_MAP = {
    "code": "代码",
    "name": "名称",
    "trade": "最新价",
    "pricechange": "涨跌额",
    "changepercent": "涨跌幅",
    "volume": "成交量",
    "amount": "成交额",
    "turnoverratio": "换手率",
    "high": "最高",
    "low": "最低",
    "open": "今开",
    "settlement": "昨收",
}


def _fetch_etf_list_sina_v2() -> Any:
    """新浪 json_v2 接口分页拉取全量 ETF 列表。

    ``fund_etf_category_sina`` 使用的 jsonp 接口对数据中心 IP 有反爬限制
    （只返回重定向脚本不含数据），导致 ECS 上 ETF 同步失败。本函数改用
    ``json_v2.php/Market_Center.getHQNodeData``（与板块成分股同族接口，
    在 ECS 上验证可用），按 ``node=etf_hq_fund`` 分页拉取全量 ETF，
    代码字段天然无 sh/sz 前缀。

    :returns: 归一化中文列名的 DataFrame（代码/名称/最新价/...）。
    :raises RuntimeError: 接口不可用或返回异常。

    :example df = _fetch_etf_list_sina_v2()  # 全量 ~1600 只 ETF
    """
    import json
    from typing import cast

    import pandas as pd
    import requests

    url = (
        "http://vip.stock.finance.sina.com.cn/quotes_service/api/"
        "json_v2.php/Market_Center.getHQNodeData"
    )
    page_size = 100
    rows: list[dict] = []
    # 全量约 1630 只（17 页），上限 30 页防御性截断
    for page in range(1, 31):
        resp = requests.get(
            url,
            params={
                "page": page,
                "num": page_size,
                "sort": "symbol",
                "asc": 1,
                "node": "etf_hq_fund",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = cast(list, json.loads(resp.text))
        if not data:
            break
        rows.extend(data)
        if len(data) < page_size:
            break

    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError("sina_v2 etf list empty")
    return df.rename(columns=_ETF_SINA_V2_COLUMN_MAP)


def _normalize_etf_columns(df: Any, source: str) -> Any:
    """将 ETF 数据源的列名归一化。

    东方财富 fund_etf_spot_em 使用中文列名（代码/名称/最新价/...），无需映射。
    同花顺 fund_etf_spot_ths 使用 基金代码/基金名称/增长率 等不同列名，需映射；
    且 THS 是净值口径，无实时价/开盘/最高/最低/成交量，这些字段留空即可。
    新浪 fund_etf_category_sina 代码带 sh/sz 前缀（如 sz159998），需去前缀。

    :param df: AkShare 返回的 DataFrame。
    :param source: 数据源标识（em/ths/sina）。
    :returns: 列名归一化后的 DataFrame。
    """
    if df is None or df.empty:
        return df

    if source == "ths":
        df = df.rename(columns=_ETF_COLUMN_MAP_THS)
    elif source == "sina":
        # 新浪源代码带 sh/sz 前缀，去掉以保持一致
        df = df.copy()
        df["代码"] = df["代码"].str.replace(r"^(sh|sz)", "", regex=True)

    return df


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
