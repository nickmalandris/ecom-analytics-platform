"""
OAuth client configuration for Google and Facebook social login.
"""

from httpx_oauth.clients.google import GoogleOAuth2
from httpx_oauth.clients.facebook import FacebookOAuth2

from src.config import settings

# ─── Google OAuth ────────────────────────────────────────

google_oauth_client = GoogleOAuth2(
    client_id=settings.google_client_id,
    client_secret=settings.google_client_secret,
)

# ─── Facebook OAuth ──────────────────────────────────────
# Reuses existing Meta app credentials from .env

facebook_oauth_client = FacebookOAuth2(
    client_id=settings.meta_app_id,
    client_secret=settings.meta_app_secret,
)
