"""
@description 邮件渲染 + LLM 解读测试。

邮件渲染用模拟数据测试模板渲染逻辑（不发真实邮件）。
LLM 解读测试降级路径（无 API Key 时用模板摘要）。
"""

from datetime import date

import pytest

from scx_stock.schema.analysis import AnalysisReport, SupportLevel


# ---------------------------------------------------------------------------
# 测试数据
# ---------------------------------------------------------------------------


def _make_report(ok: bool = True, **kwargs) -> AnalysisReport:
    """构造测试 AnalysisReport。"""
    defaults = dict(
        code="510300",
        name="沪深300ETF",
        trade_date=date(2026, 8, 12),
        close=4.75,
        change_pct=0.89,
        trend="震荡",
        ma20=4.71,
        ma60=4.84,
        support_1=SupportLevel(
            price=4.72, sources=["MA20"], distance_pct=-0.63, strength="弱"
        ),
        support_2=SupportLevel(
            price=4.66, sources=["60日低点"], distance_pct=-1.89, strength="弱"
        ),
        resistance_1=SupportLevel(
            price=4.77, sources=["Pivot R1"], distance_pct=0.42, strength="弱"
        ),
        summary="测试摘要内容",
        ok=ok,
    )
    defaults.update(kwargs)
    return AnalysisReport(**defaults)


# ---------------------------------------------------------------------------
# 邮件渲染测试
# ---------------------------------------------------------------------------


class TestEmailRender:
    """邮件模板渲染测试（不发送真实邮件）。"""

    @pytest.mark.asyncio
    async def test_render_daily_report_basic(self):
        """渲染正常报告 HTML。"""
        from scx_stock.notify.email_sender import render_daily_report

        reports = [_make_report(), _make_report(code="159915", name="创业板ETF")]
        html = await render_daily_report(reports, date(2026, 8, 12))

        assert "ETF" in html or "510300" in html
        assert "4.75" in html  # close 价格
        assert "2026-08-12" in html  # 日期
        assert "不构成" in html and "投资建议" in html  # 免责声明
        assert len(html) > 500  # 非空 HTML

    @pytest.mark.asyncio
    async def test_render_daily_report_with_failed(self):
        """含失败标的的渲染。"""
        from scx_stock.notify.email_sender import render_daily_report

        reports = [
            _make_report(),
            _make_report(ok=False, error="拉取 K 线失败", code="FAIL001"),
        ]
        html = await render_daily_report(reports)
        assert "FAIL001" in html or "分析失败" in html

    @pytest.mark.asyncio
    async def test_render_empty_reports(self):
        """空报告列表也能渲染。"""
        from scx_stock.notify.email_sender import render_daily_report

        html = await render_daily_report([], date(2026, 8, 12))
        assert "2026-08-12" in html
        assert "不构成" in html and "投资建议" in html

    @pytest.mark.asyncio
    async def test_build_message_format(self):
        """邮件消息格式正确。"""
        from scx_stock.notify.email_sender import build_message

        msg = await build_message("<p>test</p>", ["test@example.com"])
        assert msg["To"] == "test@example.com"
        assert "支撑位分析" in msg["Subject"]
        # From 头应包含编码后的发件人名（RFC2047）
        assert msg["From"] is not None

    @pytest.mark.asyncio
    async def test_send_email_no_smtp_config(self):
        """SMTP 未配置时返回 False + 错误信息。"""
        from unittest.mock import patch
        from scx_stock.notify.email_sender import send_email

        # 模拟 DB 无 SMTP 配置 + .env 也无配置
        async def mock_dynamic(keys):
            return {k: None for k in keys}

        with patch("scx_stock.notify.email_sender.get_dynamic_settings", side_effect=mock_dynamic):
            success, error = await send_email(["test@example.com"], "<p>test</p>")
            assert success is False
            assert "未配置" in error or "为空" in error


# ---------------------------------------------------------------------------
# LLM 解读降级测试
# ---------------------------------------------------------------------------


class TestInterpreterFallback:
    """LLM 解读降级路径测试（无 API Key 时用模板摘要）。"""

    @pytest.mark.asyncio
    async def test_interfall_with_no_llm(self):
        """LLM 未配置时降级为模板摘要。"""
        from unittest.mock import patch
        from scx_stock.llm.interpreter import interpret
        from scx_stock.llm.client import LlmClient

        report = _make_report(summary="")

        # mock LLM 不可用
        mock_client = LlmClient()
        with patch("scx_stock.llm.interpreter.get_llm_client", return_value=mock_client):
            with patch.object(LlmClient, "available", return_value=False):
                result = await interpret(report)
                assert result.summary != ""
                assert "震荡" in result.summary  # 模板摘要包含趋势

    @pytest.mark.asyncio
    async def test_interpret_preserves_failed_report(self):
        """失败 report 的摘要包含错误信息。"""
        from scx_stock.llm.interpreter import interpret

        report = _make_report(ok=False, error="K 线拉取失败")
        result = await interpret(report)
        assert "K 线拉取失败" in result.summary
