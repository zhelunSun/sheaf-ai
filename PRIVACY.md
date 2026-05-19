# Privacy Policy

## tl;dr

Sheaf is **local-first**. Your data stays on your machine. We don't have servers. We don't collect telemetry. We don't track you.

## What Data Leaves Your Machine

| Data | Where It Goes | Why |
|------|--------------|-----|
| Article content (title, text) | Your chosen LLM provider | AI classification and summarization |
| LLM API key | Your chosen LLM provider | Authentication for AI services |

## What Stays Local

- All fetched article content
- All generated summaries and metadata
- Your collection index
- Your tags, topics, and search history
- Your configuration

Everything lives in `./data/` (configurable via `SHEAF_DATA_DIR`) on your machine as plain Markdown + JSONL files.

## No Telemetry

Sheaf does not:
- Send crash reports
- Track usage analytics
- Log your queries
- Share any data with us or third parties

## Your Control

- Delete the `data/` directory anytime to wipe everything
- Choose your own LLM provider (self-hosted, local, or cloud)
- Export your data anytime — it's just Markdown + JSON

## Questions?

Open an issue on GitHub.
