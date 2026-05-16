"""
UC Utils — URL normalization, content hashing, platform detection, timeliness extraction.
"""
import re
import hashlib
from datetime import datetime

from uc.config import BJT


def normalize_url(url: str) -> str:
    """Normalize URL for dedup: strip trailing slash, fragment, common tracking params."""
    url = url.strip()
    if "#" in url:
        url = url.split("#")[0]
    url = url.rstrip("/")

    tracking_params = [
        "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
        "from", "isappinstalled", "nsukey", "pass_ticket",
    ]
    if "?" in url:
        base, query = url.split("?", 1)
        params = []
        for p in query.split("&"):
            key = p.split("=")[0] if "=" in p else p
            if key not in tracking_params:
                params.append(p)
        url = base + ("?" + "&".join(params) if params else "")

    # WeChat URL normalization: keep only the s parameter
    if "mp.weixin.qq.com" in url:
        match = re.search(r's=([a-zA-Z0-9_-]+)', url)
        if match:
            return f"https://mp.weixin.qq.com/s/{match.group(1)}"
    return url


def content_hash(text: str) -> str:
    """Generate a hash for content dedup (first 2000 chars, normalized)."""
    normalized = re.sub(r'\s+', ' ', text[:2000].lower().strip())
    return hashlib.md5(normalized.encode('utf-8')).hexdigest()[:12]


def detect_platform(url: str) -> str:
    """Detect source platform from URL pattern."""
    url_lower = url.lower()
    if "mp.weixin.qq.com" in url_lower:
        return "wechat"
    elif "twitter.com" in url_lower or "x.com" in url_lower:
        return "twitter"
    elif "arxiv.org" in url_lower:
        return "paper"
    elif "zhihu.com" in url_lower:
        return "web"
    elif url_lower.startswith("manual:") or not url.startswith("http"):
        return "manual"
    else:
        return "web"


def extract_timeliness(structured: dict) -> dict:
    """Extract timeliness info from LLM summary structured output."""
    deadline_text = structured.get("deadline_or_timing")
    if not deadline_text:
        return {
            "has_deadline": False,
            "deadline_date": None,
            "deadline_label": None,
            "urgency": "evergreen",
        }

    date_patterns = [
        r'(\d{4}-\d{2}-\d{2})',            # 2026-05-30
        r'(\d{4})年(\d{1,2})月(\d{1,2})日',  # 2026年5月30日
    ]

    deadline_date = None
    for pattern in date_patterns:
        match = re.search(pattern, deadline_text)
        if match:
            if len(match.groups()) == 1:
                deadline_date = match.group(1)
            elif len(match.groups()) == 3:
                deadline_date = f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
            break

    urgency = "upcoming"
    if deadline_date:
        try:
            from datetime import date as date_type
            deadline_dt = date_type.fromisoformat(deadline_date)
            today = datetime.now(BJT).date()
            days_left = (deadline_dt - today).days
            if days_left < 0:
                urgency = "expired"
            elif days_left <= 7:
                urgency = "urgent"
            elif days_left <= 30:
                urgency = "upcoming"
        except (ValueError, TypeError):
            pass

    return {
        "has_deadline": True,
        "deadline_date": deadline_date,
        "deadline_label": deadline_text if not deadline_date else None,
        "urgency": urgency,
    }
