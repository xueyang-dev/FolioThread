"""Public product branding and the compatibility boundary for legacy names."""

APP_NAME = "Folith"
APP_NAME_ZH = "译页"
TAGLINE = "Agentic Localization Workspace"
TAGLINE_ZH = "Agentic 本地化工作台"

# These are public-facing compositions used by the Chinese-first UI and the
# English console/help surfaces.  Keep the individual names available so
# documents can choose one language without duplicating literals.
APP_TITLE = f"{APP_NAME} · {TAGLINE}"
APP_TITLE_ZH = f"{APP_NAME_ZH} · {TAGLINE_ZH}"

# Persisted projects, package publication, and environment variables still
# use the old identifiers.  They are intentionally documented rather than
# silently renamed, so existing installations continue to find their data.
LEGACY_BRAND = "FolioThread"
LEGACY_PACKAGE = "foliothread"
