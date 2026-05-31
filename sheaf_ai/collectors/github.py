"""
Sheaf GitHub Repo Collector — fetch README + metadata + file tree from GitHub repos.

Uses GitHub REST API v3 (no authentication required for public repos).
Rate limits: 60 requests/hour for unauthenticated access.

Design:
  - Pure Python, uses only requests (already a dependency)
  - Best-effort: graceful degradation if API calls fail
  - Rich metadata: stars, forks, language, license, description, topics
  - File tree: first 2 directory levels for structure overview

Usage:
    from sheaf_ai.collectors.github import fetch_github_repo
    result = fetch_github_repo("https://github.com/owner/repo")
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

# GitHub API base
_GITHUB_API = "https://api.github.com"

# Common headers for GitHub API (unauthenticated)
_GITHUB_HEADERS = {
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "Sheaf-Bot/0.4.0 (https://github.com/zhelunSun/sheaf-ai)",
}


# ============================================================
# URL parsing
# ============================================================

def parse_github_url(url: str) -> Optional[dict[str, str]]:
    """Parse a GitHub URL into owner and repo components.

    Supports formats:
      - https://github.com/owner/repo
      - https://github.com/owner/repo/tree/branch
      - https://github.com/owner/repo/blob/branch/path
      - https://github.com/owner/repo/issues/123
      - etc.

    Args:
        url: A GitHub URL.

    Returns:
        dict with 'owner' and 'repo' keys, or None if not a valid GitHub repo URL.
    """
    try:
        parsed = urlparse(url)
        if parsed.netloc.lower() not in ("github.com", "www.github.com"):
            return None

        path_parts = [p for p in parsed.path.strip("/").split("/") if p]
        if len(path_parts) < 2:
            return None

        owner = path_parts[0]
        repo = path_parts[1]

        # Strip .git suffix
        if repo.endswith(".git"):
            repo = repo[:-4]

        return {"owner": owner, "repo": repo}
    except Exception:
        return None


# ============================================================
# API fetchers
# ============================================================

def _fetch_repo_metadata(owner: str, repo: str, timeout: int = 10) -> dict[str, Any]:
    """Fetch repo metadata from GitHub REST API.

    Args:
        owner: GitHub user/org name.
        repo: Repository name.
        timeout: Request timeout in seconds.

    Returns:
        dict with repo metadata, or empty dict on failure.
    """
    url = f"{_GITHUB_API}/repos/{owner}/{repo}"
    try:
        resp = requests.get(url, headers=_GITHUB_HEADERS, timeout=timeout)
        if resp.status_code == 403:
            logger.warning("GitHub API rate limit hit")
            return {"_rate_limited": True}
        resp.raise_for_status()
        data = resp.json()

        license_info = data.get("license")
        license_name = None
        if license_info and isinstance(license_info, dict):
            license_name = license_info.get("spdx_id") or license_info.get("name")

        return {
            "full_name": data.get("full_name", f"{owner}/{repo}"),
            "description": data.get("description", ""),
            "stars": data.get("stargazers_count", 0),
            "forks": data.get("forks_count", 0),
            "watchers": data.get("subscribers_count", 0),
            "open_issues": data.get("open_issues_count", 0),
            "language": data.get("language"),
            "license": license_name,
            "topics": data.get("topics", []),
            "default_branch": data.get("default_branch", "main"),
            "created_at": data.get("created_at"),
            "updated_at": data.get("pushed_at") or data.get("updated_at"),
            "homepage": data.get("homepage", ""),
            "is_archived": data.get("archived", False),
            "is_fork": data.get("fork", False),
            "_rate_limited": False,
        }
    except Exception as e:
        logger.warning(f"GitHub metadata fetch failed for {owner}/{repo}: {e}")
        return {"_rate_limited": False, "_error": str(e)}


def _fetch_readme(owner: str, repo: str, timeout: int = 10) -> str:
    """Fetch README content from GitHub REST API.

    Tries common README filenames: README.md, README.rst, README, README.txt

    Args:
        owner: GitHub user/org name.
        repo: Repository name.
        timeout: Request timeout in seconds.

    Returns:
        README content string, or empty string if not found.
    """
    readme_names = ["README.md", "README.rst", "README", "README.txt"]
    for name in readme_names:
        url = f"{_GITHUB_API}/repos/{owner}/{repo}/contents/{name}"
        try:
            resp = requests.get(url, headers=_GITHUB_HEADERS, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                import base64
                content = data.get("content", "")
                if content:
                    # GitHub returns base64-encoded content
                    return base64.b64decode(content).decode("utf-8", errors="replace")
            elif resp.status_code == 403:
                # Rate limited — stop trying
                logger.warning("GitHub API rate limit hit during README fetch")
                break
        except Exception as e:
            logger.debug(f"README fetch failed for {name}: {e}")
            continue

    return ""


def _fetch_file_tree(owner: str, repo: str, branch: str = "main", max_depth: int = 2, timeout: int = 10) -> list[dict[str, Any]]:
    """Fetch file tree (first N levels) from GitHub REST API.

    Uses the Git Trees API with recursive option, then filters to max_depth.

    Args:
        owner: GitHub user/org name.
        repo: Repository name.
        branch: Branch name (default "main").
        max_depth: Maximum directory depth to include.
        timeout: Request timeout in seconds.

    Returns:
        List of dicts with path, type (file/dir), and depth.
    """
    url = f"{_GITHUB_API}/repos/{owner}/{repo}/git/trees/{branch}"
    params = {"recursive": "1"}
    try:
        resp = requests.get(url, headers=_GITHUB_HEADERS, params=params, timeout=timeout)
        if resp.status_code == 403:
            logger.warning("GitHub API rate limit hit during tree fetch")
            return []
        resp.raise_for_status()
        data = resp.json()
        tree = data.get("tree", [])

        result = []
        for item in tree:
            path = item.get("path", "")
            item_type = item.get("type", "blob")
            depth = path.count("/")

            if depth > max_depth:
                continue

            # For directories at max_depth, skip their children
            if depth == max_depth and item_type == "tree":
                result.append({"path": path + "/", "type": "dir", "depth": depth})
                continue

            display_type = "dir" if item_type == "tree" else "file"
            result.append({"path": path, "type": display_type, "depth": depth})

        return result
    except Exception as e:
        logger.warning(f"File tree fetch failed for {owner}/{repo}: {e}")
        return []


# ============================================================
# Formatting helpers
# ============================================================

def _format_file_tree(tree: list[dict[str, Any]]) -> str:
    """Format file tree into a readable text representation.

    Args:
        tree: List of tree items from _fetch_file_tree.

    Returns:
        Formatted string representation of the file tree.
    """
    if not tree:
        return ""

    lines = []
    for item in tree:
        path = item["path"]
        item_type = item["type"]
        indent = "  " * item["depth"]
        icon = "\U0001f4c1" if item_type == "dir" else "\U0001f4c4"  # folder / page
        lines.append(f"{indent}{icon} {path.split('/')[-1]}")

    return "\n".join(lines)


def _build_repo_text(
    metadata: dict[str, Any],
    readme_content: str,
    file_tree_text: str,
) -> str:
    """Build the combined text representation of a GitHub repo.

    Args:
        metadata: Repo metadata dict.
        readme_content: README content string.
        file_tree_text: Formatted file tree string.

    Returns:
        Combined text for storage/crystallization.
    """
    parts = []

    # Header
    full_name = metadata.get("full_name", "")
    description = metadata.get("description", "")
    if full_name:
        parts.append(f"# {full_name}")
    if description:
        parts.append(f"\n> {description}")

    # Stats line
    stats = []
    if metadata.get("stars") is not None:
        stats.append(f"Stars: {metadata['stars']}")
    if metadata.get("forks") is not None:
        stats.append(f"Forks: {metadata['forks']}")
    if metadata.get("language"):
        stats.append(f"Language: {metadata['language']}")
    if metadata.get("license"):
        stats.append(f"License: {metadata['license']}")
    if stats:
        parts.append("\n" + " | ".join(stats))

    # Topics
    topics = metadata.get("topics", [])
    if topics:
        parts.append(f"\nTopics: {', '.join(topics)}")

    # File tree
    if file_tree_text:
        parts.append("\n## Project Structure\n")
        parts.append("```\n" + file_tree_text + "\n```")

    # README
    if readme_content:
        # Truncate very long READMEs
        max_readme = 8000
        readme = readme_content[:max_readme]
        if len(readme_content) > max_readme:
            readme += "\n\n... (truncated)"
        parts.append("\n## README\n")
        parts.append(readme)

    return "\n".join(parts)


# ============================================================
# Main entry point
# ============================================================

def fetch_github_repo(url: str, timeout: int = 10, **kwargs) -> dict[str, Any]:
    """Fetch a GitHub repo's README + metadata + file tree.

    This is the main entry point for the GitHub repo collector.

    Args:
        url: GitHub repo URL (e.g., https://github.com/owner/repo).
        timeout: API request timeout in seconds.
        **kwargs: Additional arguments (ignored).

    Returns:
        dict with keys:
            success: bool
            title: str (repo full_name)
            text: str (combined: metadata + file tree + README)
            method: str ("github-api")
            error: str or None
            meta: dict with raw metadata
    """
    # Parse URL
    parsed = parse_github_url(url)
    if parsed is None:
        return {
            "success": False,
            "title": "",
            "text": "",
            "method": "github-api",
            "error": "Not a valid GitHub repo URL",
            "meta": {},
        }

    owner = parsed["owner"]
    repo = parsed["repo"]

    logger.info(f"Fetching GitHub repo: {owner}/{repo}")

    # Fetch metadata (always try)
    metadata = _fetch_repo_metadata(owner, repo, timeout=timeout)

    if metadata.get("_rate_limited"):
        return {
            "success": False,
            "title": f"{owner}/{repo}",
            "text": "",
            "method": "github-api",
            "error": "GitHub API rate limit exceeded (60 req/hr for unauthenticated)",
            "meta": {},
        }

    # Fetch README (best-effort)
    readme_content = _fetch_readme(owner, repo, timeout=timeout)

    # Fetch file tree (best-effort)
    branch = metadata.get("default_branch", "main")
    file_tree = _fetch_file_tree(owner, repo, branch=branch, max_depth=2, timeout=timeout)
    file_tree_text = _format_file_tree(file_tree)

    # Build combined text
    text = _build_repo_text(metadata, readme_content, file_tree_text)
    title = metadata.get("full_name", f"{owner}/{repo}")

    # Determine success: we need at least metadata
    has_content = bool(readme_content or file_tree or metadata.get("description"))
    meta_error = metadata.pop("_error", None)

    return {
        "success": has_content,
        "title": title,
        "text": text,
        "method": "github-api",
        "error": None if has_content else (meta_error or "No content extracted"),
        "meta": {
            "source": "github",
            "owner": owner,
            "repo": repo,
            "url": url,
            "stars": metadata.get("stars", 0),
            "forks": metadata.get("forks", 0),
            "language": metadata.get("language"),
            "license": metadata.get("license"),
            "topics": metadata.get("topics", []),
            "default_branch": branch,
            "file_count": len(file_tree),
            "readme_length": len(readme_content),
            "is_archived": metadata.get("is_archived", False),
            "is_fork": metadata.get("is_fork", False),
        },
        "quality": {
            "ok": has_content,
            "score": 4 if readme_content and file_tree else (2 if readme_content else 1),
            "length": len(text),
            "reason": "github_repo" if has_content else "empty",
        },
    }
