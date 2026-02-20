"""
Report builder: Assembles the agent's output into a formatted HTML email.

Usage:
    from src.reports.builder import build_weekly_report
    html = build_weekly_report(
        report_text="...",
        tenant_name="Test Store AU",
        period_start="2026-02-13",
        period_end="2026-02-19",
    )
"""

from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

TEMPLATE_DIR = Path(__file__).parent / "templates"


def _get_jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=True,
    )


def _format_report_body(report_text: str) -> str:
    """
    Convert the agent's plain-text report into HTML-safe content.

    Handles section headers, bullet points, and numbered lists.
    """
    lines = report_text.strip().split("\n")
    html_parts = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            html_parts.append("<br>")
            continue

        # Section headers (### or all caps or contains "SUMMARY", "INSIGHTS", "WINS")
        is_header = False
        if stripped.startswith("###"):
            stripped = stripped.lstrip("#").strip()
            is_header = True
        elif stripped.isupper() and len(stripped) > 5:
            is_header = True
        elif any(kw in stripped.upper() for kw in ["WEEKLY PERFORMANCE", "TOP INSIGHTS", "QUICK WINS"]):
            is_header = True

        if is_header:
            html_parts.append(
                f'<div class="section-title">{stripped}</div>'
            )
        elif stripped.startswith(("- ", "* ")):
            # Bullet point
            content = stripped[2:]
            html_parts.append(f"&bull; {content}<br>")
        elif len(stripped) > 1 and stripped[0].isdigit() and stripped[1] in (".", ")"):
            # Numbered list
            html_parts.append(f"{stripped}<br>")
        else:
            html_parts.append(f"{stripped}<br>")

    return "\n".join(html_parts)


def build_weekly_report(
    report_text: str,
    tenant_name: str,
    period_start: str,
    period_end: str,
) -> str:
    """
    Build the final HTML email from the agent's report text.

    Returns the full HTML string ready for email delivery.
    """
    env = _get_jinja_env()
    template = env.get_template("weekly.html")

    report_body = _format_report_body(report_text)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return template.render(
        report_body=report_body,
        tenant_name=tenant_name,
        period_start=period_start,
        period_end=period_end,
        generated_at=generated_at,
    )
