"""
@description 支撑位分析引擎测试：indicators / support / trend / engine / fallback_summary / 新鲜度校验。
"""

import contextlib
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scx_stock.analysis.engine import analyze, fallback_summary
from scx_stock.analysis.indicators import (
    calc_ma,
    calc_pivot_points,
    calc_recent_high,
    calc_recent_low,
    to_dataframe,
)
from scx_stock.analysis.support import _strength_label, find_resistances, find_supports
from scx_stock.analysis.trend import judge_trend
from scx_stock.scheduler import analysis_job
from scx_stock.schema.kline import Kline, KlineBar
from scx_stock.storage import repo as repo_mod


# ---------------------------------------------------------------------------
# 测试数据工厂
# ---------------------------------------------------------------------------


def _make_bars(n: int = 120, base: float = 4.0, trend: str = "up") -> list[KlineBar]:
    """生成模拟 K 线数据。

    :param n: K 线根数。
    :param base: 基准价格。
    :param trend: up（递增）/ down（递减）/ flat（横盘）。
    :returns: KlineBar 列表（按日期升序）。
    """
    bars = []
    for i in range(n):
        d = date(2026, 1, 1) + timedelta(days=i)
        if trend == "up":
            close = round(base + i * 0.01, 3)
        elif trend == "down":
            close = round(base - i * 0.01, 3)
        else:
            close = round(base + (i % 10 - 5) * 0.02, 3)
        bars.append(
            KlineBar(
                trade_date=d,
                open=round(close - 0.02, 3),
                close=close,
                high=round(close + 0.03, 3),
                low=round(close - 0.03, 3),
                volume=100000 + i * 100,
            )
        )
    return bars


def _make_kline(n: int = 120, trend: str = "up") -> Kline:
    """构造 Kline 对象。"""
    return Kline(code="TEST", name="测试ETF", bars=_make_bars(n=n, trend=trend))


# ---------------------------------------------------------------------------
# indicators 测试
# ---------------------------------------------------------------------------


class TestIndicators:
    """技术指标计算测试。"""

    def test_calc_ma_basic(self):
        """MA 计算正确返回最新均值。"""
        import pandas as pd

        close = pd.Series([1, 2, 3, 4, 5], dtype=float)
        ma = calc_ma(close, 3)
        assert ma is not None
        assert ma == pytest.approx((3 + 4 + 5) / 3)

    def test_calc_ma_insufficient_data(self):
        """数据不足返回 None。"""
        import pandas as pd

        close = pd.Series([1, 2], dtype=float)
        assert calc_ma(close, 20) is None

    def test_calc_pivot_points(self):
        """Pivot Point 计算正确。"""
        result = calc_pivot_points(high=4.3, low=4.1, close=4.2)
        assert result["pivot"] == pytest.approx(4.2, abs=0.01)
        assert result["r1"] > result["pivot"]
        assert result["s1"] < result["pivot"]
        assert result["r2"] > result["r1"]
        assert result["s2"] < result["s1"]

    def test_calc_recent_low(self):
        """近 N 日最低价。"""
        df = to_dataframe(_make_bars(n=30))
        low = calc_recent_low(df, 10)
        assert low is not None
        assert low > 0

    def test_calc_recent_high(self):
        """近 N 日最高价。"""
        df = to_dataframe(_make_bars(n=30))
        high = calc_recent_high(df, 10)
        assert high is not None
        assert high > 0

    def test_to_dataframe_empty(self):
        """空列表返回空 DataFrame。"""
        df = to_dataframe([])
        assert df.empty
        assert "close" in df.columns


# ---------------------------------------------------------------------------
# support 测试
# ---------------------------------------------------------------------------


class TestSupport:
    """支撑位/压力位筛选测试。"""

    def test_find_supports_below_price(self):
        """支撑位应低于当前价。"""
        df = to_dataframe(_make_bars(n=120))
        current = float(df["close"].iloc[-1])
        supports = find_supports(df, current, top_n=2)
        for s in supports:
            assert s.price < current

    def test_find_resistances_above_price(self):
        """压力位应高于当前价。"""
        df = to_dataframe(_make_bars(n=120))
        current = float(df["close"].iloc[-1])
        resistances = find_resistances(df, current, top_n=1)
        for r in resistances:
            assert r.price > current

    def test_strength_label(self):
        """强度标签按命中来源数划分。"""
        assert _strength_label(3) == "强"
        assert _strength_label(2) == "中"
        assert _strength_label(1) == "弱"


# ---------------------------------------------------------------------------
# trend 测试
# ---------------------------------------------------------------------------


class TestTrend:
    """趋势判断测试。"""

    def test_uptrend(self):
        """递增数据判定为多头。"""
        import pandas as pd

        close = pd.Series(list(range(1, 81)), dtype=float)
        assert judge_trend(close) == "多头"

    def test_downtrend(self):
        """递减数据判定为空头。"""
        import pandas as pd

        close = pd.Series(list(range(80, 0, -1)), dtype=float)
        assert judge_trend(close) == "空头"

    def test_flat_trend(self):
        """横盘数据判定为震荡。"""
        import pandas as pd

        # 交替涨跌，均线缠绕
        values = []
        for i in range(80):
            values.append(10 + (1 if i % 2 == 0 else -1) * (i % 3))
        close = pd.Series(values, dtype=float)
        trend = judge_trend(close)
        assert trend in ("震荡", "多头", "空头")

    def test_empty_close(self):
        """空序列返回未知。"""
        import pandas as pd

        assert judge_trend(pd.Series([], dtype=float)) == "未知"

    def test_insufficient_data(self):
        """数据不足返回'数据不足'。"""
        import pandas as pd

        close = pd.Series([1, 2, 3], dtype=float)
        assert judge_trend(close) == "数据不足"


# ---------------------------------------------------------------------------
# engine 测试
# ---------------------------------------------------------------------------


class TestEngine:
    """分析引擎编排测试。"""

    def test_analyze_uptrend(self):
        """上涨趋势分析成功，趋势为多头。"""
        kline = _make_kline(n=120, trend="up")
        report = analyze(kline)
        assert report.ok is True
        assert report.code == "TEST"
        assert report.trend == "多头"
        assert report.close is not None
        assert report.close > 0

    def test_analyze_supports_below_close(self):
        """分析后支撑位应低于收盘价。"""
        kline = _make_kline(n=120, trend="flat")
        report = analyze(kline)
        assert report.ok is True
        if report.support_1:
            assert report.support_1.price < report.close
        if report.resistance_1:
            assert report.resistance_1.price > report.close

    def test_analyze_insufficient_data(self):
        """K 线不足 30 根返回 ok=False。"""
        kline = _make_kline(n=20, trend="up")
        report = analyze(kline)
        assert report.ok is False
        assert "不足" in report.error

    def test_fallback_summary_with_report(self):
        """降级摘要包含趋势和支撑位。"""
        kline = _make_kline(n=120, trend="up")
        report = analyze(kline)
        summary = fallback_summary(report)
        assert "多头" in summary
        assert "支撑" in summary

    def test_fallback_summary_failed_report(self):
        """失败 report 的降级摘要含错误信息。"""
        kline = _make_kline(n=20, trend="up")
        report = analyze(kline)
        summary = fallback_summary(report)
        assert "分析失败" in summary


# ---------------------------------------------------------------------------
# _analyze_one K 线新鲜度校验测试
# ---------------------------------------------------------------------------

_FRESH_DAY = date(2026, 8, 17)  # 周一，最近交易日
_STALE_DAY = date(2026, 8, 14)  # 上周五，陈旧


def _make_bars_ending(end: date, n: int = 120) -> list[KlineBar]:
    """生成结束于 end 日、缓慢递增的 K 线（日期连续，仅供日期新鲜度比较）。

    :param end: 最后一根 bar 的交易日。
    :param n: K 线根数。
    :returns: KlineBar 列表（按日期升序）。
    """
    start = end - timedelta(days=n - 1)
    bars = []
    for i in range(n):
        close = round(4.0 + i * 0.01, 3)
        bars.append(
            KlineBar(
                trade_date=start + timedelta(days=i),
                open=round(close - 0.02, 3),
                close=close,
                high=round(close + 0.03, 3),
                low=round(close - 0.03, 3),
                volume=100000 + i * 100,
            )
        )
    return bars


def _identity_interpret() -> AsyncMock:
    """构造原样返回 report 的 interpret 替身，避免测试触发 LLM。"""
    return AsyncMock(side_effect=lambda r: r)


class TestAnalyzeOneFreshness:
    """_analyze_one 应拒绝陈旧 K 线，确保报告 trade_date 不落后于最近交易日。"""

    @pytest.mark.asyncio
    async def test_fresh_db_kline_skips_provider(self):
        """DB K 线已覆盖最近交易日时直接使用，不回退 Provider。"""
        kline = Kline(code="159327", bars=_make_bars_ending(_FRESH_DAY))
        with (
            patch.object(analysis_job.repo, "load_kline", new=AsyncMock(return_value=kline)),
            patch.object(analysis_job.repo, "latest_trade_date", new=AsyncMock(return_value=_FRESH_DAY)),
            patch.object(analysis_job.AkshareProvider, "get_kline", new=AsyncMock()) as m_get,
            patch.object(analysis_job, "interpret", new=_identity_interpret()),
        ):
            report = await analysis_job._analyze_one(
                analysis_job.AkshareProvider(), "159327", 120, name="测试ETF"
            )

        assert report.ok is True
        assert report.trade_date == _FRESH_DAY
        m_get.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_stale_db_falls_back_to_provider(self):
        """DB K 线落后于最近交易日时回退 Provider 重拉并回填 DB。"""
        stale = Kline(code="159327", bars=_make_bars_ending(_STALE_DAY))
        fresh = Kline(code="159327", bars=_make_bars_ending(_FRESH_DAY))
        with (
            patch.object(analysis_job.repo, "load_kline", new=AsyncMock(return_value=stale)),
            patch.object(analysis_job.repo, "latest_trade_date", new=AsyncMock(return_value=_FRESH_DAY)),
            patch.object(analysis_job.AkshareProvider, "get_kline", new=AsyncMock(return_value=fresh)),
            patch.object(analysis_job.repo, "upsert_klines", new=AsyncMock(return_value=1)) as m_up,
            patch.object(analysis_job, "interpret", new=_identity_interpret()),
        ):
            report = await analysis_job._analyze_one(
                analysis_job.AkshareProvider(), "159327", 120, name="测试ETF"
            )

        assert report.ok is True
        assert report.trade_date == _FRESH_DAY
        m_up.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stale_db_provider_error_fails_honestly(self):
        """DB 过期且 Provider 拉取失败时如实返回 ok=False，不用旧数据生成报告。"""
        stale = Kline(code="159327", bars=_make_bars_ending(_STALE_DAY))
        with (
            patch.object(analysis_job.repo, "load_kline", new=AsyncMock(return_value=stale)),
            patch.object(analysis_job.repo, "latest_trade_date", new=AsyncMock(return_value=_FRESH_DAY)),
            patch.object(
                analysis_job.AkshareProvider,
                "get_kline",
                new=AsyncMock(side_effect=RuntimeError("all sources failed")),
            ),
            patch.object(analysis_job, "interpret", new=_identity_interpret()),
        ):
            report = await analysis_job._analyze_one(
                analysis_job.AkshareProvider(), "159327", 120, name="测试ETF"
            )

        assert report.ok is False
        assert "未更新到" in report.error

    @pytest.mark.asyncio
    async def test_stale_db_provider_also_stale_fails_honestly(self):
        """DB 与数据源都落后于最近交易日时如实返回 ok=False。"""
        stale = Kline(code="159327", bars=_make_bars_ending(_STALE_DAY))
        with (
            patch.object(analysis_job.repo, "load_kline", new=AsyncMock(return_value=stale)),
            patch.object(analysis_job.repo, "latest_trade_date", new=AsyncMock(return_value=_FRESH_DAY)),
            patch.object(analysis_job.AkshareProvider, "get_kline", new=AsyncMock(return_value=stale)),
            patch.object(analysis_job, "interpret", new=_identity_interpret()),
        ):
            report = await analysis_job._analyze_one(
                analysis_job.AkshareProvider(), "159327", 120, name="测试ETF"
            )

        assert report.ok is False
        assert "未更新到" in report.error


class TestLatestTradeDate:
    """latest_trade_date：取 ≤ 截止日的最近交易日。"""

    @pytest.mark.asyncio
    async def test_reads_calendar_from_db(self):
        """DB 日历可用时返回 ≤ 截止日的最大开市日。"""
        fake_result = MagicMock()
        fake_result.scalar_one_or_none.return_value = date(2026, 8, 17)

        @contextlib.asynccontextmanager
        async def _factory_ctx():
            yield MagicMock(execute=AsyncMock(return_value=fake_result))

        with patch.object(repo_mod, "get_session_factory", new=lambda: _factory_ctx):
            result = await repo_mod.latest_trade_date(date(2026, 8, 17))

        assert result == date(2026, 8, 17)

    @pytest.mark.asyncio
    async def test_falls_back_to_weekday_when_db_down(self):
        """DB 不可用时回退星期推算：周日活动日取上周五。"""

        def _boom():
            raise RuntimeError("db down")

        with patch.object(repo_mod, "get_session_factory", new=_boom):
            result = await repo_mod.latest_trade_date(date(2026, 8, 16))  # 周日

        assert result == date(2026, 8, 14)  # 上周五
