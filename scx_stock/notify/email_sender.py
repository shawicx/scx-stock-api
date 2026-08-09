"""
@description 邮件渲染与异步发送，基于 jinja2 模板 + aiosmtplib。
"""

import logging
from datetime import date
from pathlib import Path

from aiosmtplib import SMTP
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from jinja2 import Environment, FileSystemLoader, select_autoescape

from scx_stock.config.settings import get_settings
from scx_stock.schema.analysis import AnalysisReport

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"

_jinja_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)


def _format_pct(val: float | None) -> str:
    """格式化百分比，None 返回 '-'。

    :param val: 百分比值。
    :returns: 格式化字符串。
    """
    if val is None:
        return "-"
    return f"{val:+.2f}"


def _report_to_template_item(report: AnalysisReport) -> dict:
    """把 AnalysisReport 转为模板所需字段字典。

    :param report: 分析结果。
    :returns: 模板字段字典。
    """
    return {
        "code": report.code,
        "name": report.name or report.code,
        "ok": report.ok,
        "error": report.error,
        "trend": report.trend,
        "close": report.close,
        "change_pct": report.change_pct,
        "support_1_price": report.support_1.price if report.support_1 else None,
        "support_1_pct": _format_pct(report.support_1.distance_pct) if report.support_1 else None,
        "support_2_price": report.support_2.price if report.support_2 else None,
        "support_2_pct": _format_pct(report.support_2.distance_pct) if report.support_2 else None,
        "resistance_1_price": report.resistance_1.price if report.resistance_1 else None,
        "resistance_1_pct": _format_pct(report.resistance_1.distance_pct) if report.resistance_1 else None,
        "summary": report.summary,
    }


def render_daily_report(reports: list[AnalysisReport], report_date: date | None = None) -> str:
    """渲染每日分析报告 HTML 邮件内容。

    :param reports: 分析结果列表。
    :param report_date: 报告日期，默认今天。
    :returns: HTML 字符串。
    """
    s = get_settings()
    template = _jinja_env.get_template("daily_report.html")
    return template.render(
        report_date=(report_date or date.today()).strftime("%Y-%m-%d"),
        total=len(reports),
        success=sum(1 for r in reports if r.ok),
        failed=sum(1 for r in reports if not r.ok),
        items=[_report_to_template_item(r) for r in reports],
        from_name=s.smtp_from_name,
    )


def build_message(html: str, recipients: list[str]) -> MIMEMultipart:
    """构造带 HTML 正文的多部分邮件。

    :param html: HTML 正文。
    :param recipients: 收件人列表（用于显示 To 头）。
    :returns: MIMEMultipart 邮件对象。
    """
    s = get_settings()
    msg = MIMEMultipart("alternative")
    subject_date = date.today().strftime("%Y-%m-%d")
    msg["Subject"] = f"【每日支撑位分析】{subject_date}"
    msg["From"] = f"{s.smtp_from_name} <{s.smtp_user}>" if s.smtp_from_name else s.smtp_user
    msg["To"] = ", ".join(recipients)

    # 纯文本兜底
    text_body = "本邮件为 HTML 格式，请使用支持 HTML 的客户端查看。"
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))
    return msg


async def send_email(recipients: list[str], html: str, retries: int = 2) -> bool:
    """异步发送邮件，失败自动重试。

    :param recipients: 收件人邮箱列表。
    :param html: HTML 正文。
    :param retries: 失败重试次数。
    :returns: 是否全部发送成功。
    """
    s = get_settings()
    if not s.smtp_host or not s.smtp_user:
        logger.warning("SMTP 未配置，跳过邮件发送")
        return False
    if not recipients:
        logger.warning("收件人列表为空，跳过邮件发送")
        return False

    msg = build_message(html, recipients)
    last_error: Exception | None = None

    for attempt in range(1, retries + 2):
        try:
            smtp = SMTP(
                hostname=s.smtp_host,
                port=s.smtp_port,
                use_tls=s.smtp_use_ssl,
                timeout=30,
            )
            await smtp.connect()
            await smtp.login(s.smtp_user, s.smtp_password)
            await smtp.send_message(msg)
            await smtp.quit()
            logger.info("邮件发送成功：收件人=%s（第 %d 次尝试）", recipients, attempt)
            return True
        except Exception as e:  # noqa: BLE001
            last_error = e
            logger.warning("邮件发送失败（第 %d 次）: %s", attempt, e)
            if attempt <= retries:
                import asyncio
                await asyncio.sleep(2 * attempt)

    logger.error("邮件发送最终失败: %s", last_error)
    return False
