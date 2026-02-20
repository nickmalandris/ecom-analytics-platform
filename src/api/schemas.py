"""
Pydantic schemas for API request/response models.
"""

from datetime import datetime

from pydantic import BaseModel, Field


# ── Tenant schemas ──────────────────────────────

class TenantCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    shopify_store_url: str | None = None
    meta_account_id: str | None = None
    email_recipients: list[str] = Field(default_factory=list)


class TenantUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    shopify_store_url: str | None = None
    meta_account_id: str | None = None
    email_recipients: list[str] | None = None


class TenantResponse(BaseModel):
    id: int
    name: str
    shopify_store_url: str | None = None
    meta_account_id: str | None = None
    api_key: str
    email_recipients: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ── Report schemas ──────────────────────────────

class ReportRequest(BaseModel):
    end_date: str | None = Field(
        None,
        description="Report end date YYYY-MM-DD. Defaults to yesterday.",
    )


class ReportResponse(BaseModel):
    tenant_id: int
    period_start: str
    period_end: str
    report_text: str
    html_report: str


class ReportStatusResponse(BaseModel):
    status: str
    message: str
