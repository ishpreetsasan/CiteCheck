"""
citecheck.config
----------------
Runtime configuration and environment loading.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root if present
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# API Configuration
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

# HTTP Client Safeguards
CITECHECK_TIMEOUT_SECONDS: int = int(os.getenv("CITECHECK_TIMEOUT_SECONDS", "4"))
USER_AGENT: str = "CiteCheck-Auditing-Engine/1.0 (AI Answer Verification Bot)"

# Environment Mode
CITECHECK_ENV: str = os.getenv("CITECHECK_ENV", "development")
