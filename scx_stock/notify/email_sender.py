"""
@description 邮件渲染与异步发送，基于 jinja2 模板 + aiosmtplib。

SMTP 配置优先读 DB app_setting 表（前端配置页面修改即时生效），回退 .env。
"""

import asyncio
import logging
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path

from aiosmtplib import SMTP
from jinja2 import Environment, FileSystemLoader, select_autoescape

from scx_stock.config.dynamic import get_dynamic_settings
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


async def render_daily_report(
    reports: list[AnalysisReport], report_date: date | None = None
) -> str:
    """渲染每日分析报告 HTML 邮件内容。

    :param reports: 分析结果列表。
    :param report_date: 报告日期，默认今天。
    :returns: HTML 字符串。
    """
    cfg = await get_dynamic_settings(["smtp_from_name"])
    template = _jinja_env.get_template("daily_report.html")
    return template.render(
        report_date=(report_date or date.today()).strftime("%Y-%m-%d"),
        total=len(reports),
        success=sum(1 for r in reports if r.ok),
        failed=sum(1 for r in reports if not r.ok),
        items=[_report_to_template_item(r) for r in reports],
        from_name=cfg.get("smtp_from_name") or "ETF日报",
    )


async def build_message(html: str, recipients: list[str]) -> MIMEMultipart:
    """构造带 HTML 正文的多部分邮件。

    :param html: HTML 正文。
    :param recipients: 收件人列表（用于显示 To 头）。
    :returns: MIMEMultipart 邮件对象。
    """
    cfg = await get_dynamic_settings(["smtp_user", "smtp_from_name"])
    from_name = cfg.get("smtp_from_name") or ""
    smtp_user = cfg.get("smtp_user") or ""

    msg = MIMEMultipart("alternative")
    subject_date = date.today().strftime("%Y-%m-%d")
    msg["Subject"] = f"【每日支撑位分析】{subject_date}"
    # 用 formataddr 正确编码中文发件人名（RFC2047），避免 QQ 邮箱 550 报错
    msg["From"] = formataddr((from_name, smtp_user)) if from_name else smtp_user
    msg["To"] = ", ".join(recipients)

    # 纯文本兜底
    text_body = "本邮件为 HTML 格式，请使用支持 HTML 的客户端查看。"
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))
    return msg


async def send_email(
    recipients: list[str], html: str, retries: int = 2
) -> tuple[bool, str]:
    """异步发送邮件，失败自动重试。

    SMTP 配置优先读 DB（前端配置页面修改即时生效），回退 .env。

    :param recipients: 收件人邮箱列表。
    :param html: HTML 正文。
    :param retries: 失败重试次数。
    :returns: (是否成功, 错误原因或空字符串)。
    """
    cfg = await get_dynamic_settings([
        "smtp_host", "smtp_port", "smtp_user", "smtp_password", "smtp_use_ssl",
    ])
    smtp_host = cfg.get("smtp_host") or ""
    smtp_user = cfg.get("smtp_user") or ""
    smtp_password = cfg.get("smtp_password") or ""
    smtp_port = int(cfg.get("smtp_port") or 465)
    # smtp_use_ssl 来源可能是 bool（.env Settings）或 str（DB app_setting）
    use_ssl_raw = cfg.get("smtp_use_ssl")
    if isinstance(use_ssl_raw, bool):
        smtp_use_ssl = use_ssl_raw
    else:
        smtp_use_ssl = str(use_ssl_raw or "true").lower() in ("true", "1", "yes")

    if not smtp_host or not smtp_user:
        return False, "SMTP 主机或账号未配置"
    if not recipients:
        return False, "收件人列表为空"

    msg = await build_message(html, recipients)
    last_error: Exception | None = None

    # 以端口为权威判断加密方式：465=隐式 SSL，587/其他=STARTTLS
    # 不依赖 use_ssl 配置（用户可能配了 587 但忘取消勾选 use_ssl）
    use_implicit_tls = smtp_port == 465

    for attempt in range(1, retries + 2):
        try:
            smtp = SMTP(hostname=smtp_host, port=smtp_port, timeout=30)
            if use_implicit_tls:
                # 465: 隐式 SSL，连接时即加密
                await smtp.connect(use_tls=True)
            else:
                # 587/其他: STARTTLS，连接时升级加密（参数传给 connect 而非单独调 starttls）
                await smtp.connect(use_tls=False, start_tls=True)

            await smtp.login(smtp_user, smtp_password)
            await smtp.send_message(msg)
            await smtp.quit()
            logger.info("邮件发送成功：收件人=%s（第 %d 次尝试）", recipients, attempt)
            return True, ""
        except Exception as e:  # noqa: BLE001
            last_error = e
            logger.warning("邮件发送失败（第 %d 次）: %s", attempt, e)
            if attempt <= retries:
                await asyncio.sleep(2 * attempt)

    error_msg = f"{type(last_error).__name__}: {last_error}" if last_error else "未知错误"
    logger.error("邮件发送最终失败: %s", error_msg)
    return False, error_msg
