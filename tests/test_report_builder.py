"""
Tests for the report builder (text -> HTML conversion).
"""

from src.reports.builder import _format_report_body, build_weekly_report


class TestFormatReportBody:
    def test_section_headers(self):
        result = _format_report_body("### WEEKLY PERFORMANCE SUMMARY\nSome text")
        assert 'class="section-title"' in result

    def test_all_caps_header(self):
        result = _format_report_body("WEEKLY PERFORMANCE SUMMARY\nSome text")
        assert 'class="section-title"' in result

    def test_bullet_points(self):
        result = _format_report_body("- Bullet one\n- Bullet two")
        assert "&bull;" in result

    def test_numbered_list(self):
        result = _format_report_body("1. First item\n2. Second item")
        assert "1. First item" in result
        assert "2. Second item" in result

    def test_empty_lines_become_br(self):
        result = _format_report_body("Line one\n\nLine two")
        assert "<br>" in result

    def test_plain_text_preserved(self):
        result = _format_report_body("Revenue: $48,230 AUD")
        assert "Revenue:" in result
        assert "$48,230" in result


class TestBuildWeeklyReport:
    def test_returns_html(self):
        html = build_weekly_report("Test report", "My Store", "2026-01-01", "2026-01-07")
        assert html.startswith("<!DOCTYPE html>")

    def test_contains_tenant_name(self):
        html = build_weekly_report("Test", "Test Store AU", "2026-01-01", "2026-01-07")
        assert "Test Store AU" in html

    def test_contains_period(self):
        html = build_weekly_report("Test", "Store", "2026-02-13", "2026-02-19")
        assert "2026-02-13" in html
        assert "2026-02-19" in html

    def test_contains_generated_timestamp(self):
        html = build_weekly_report("Test", "Store", "2026-01-01", "2026-01-07")
        assert "Generated on" in html

    def test_report_body_not_escaped(self):
        """HTML in report body should render, not be escaped."""
        html = build_weekly_report("### HEADER\nContent", "Store", "2026-01-01", "2026-01-07")
        assert '<div class="section-title">' in html
        assert "&lt;div" not in html

    def test_handles_empty_report(self):
        html = build_weekly_report("", "Store", "2026-01-01", "2026-01-07")
        assert "<!DOCTYPE html>" in html
