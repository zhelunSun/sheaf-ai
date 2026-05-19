# Security Policy

## Reporting Vulnerabilities

Please open a GitHub issue or email security concerns directly.

## Local-First Security Model

Sheaf follows a **local-first security model**:

### What You Control

- **Data storage**: All content stored locally in `./data/` (configurable via `SHEAF_DATA_DIR`)
- **LLM provider**: You choose and configure your own API endpoint
- **API keys**: Stored in your local environment or `.env` file

### What We Don't Do

- No remote servers
- No data synchronization to external services
- No bundled API keys or backdoors
- No auto-update mechanism (you control when to upgrade)

### Best Practices

1. **Protect your API key**: Don't commit `.env` files to version control
2. **Review fetched content**: Sheaf fetches URLs you provide — only collect trusted sources
3. **Keep dependencies updated**: `pip install --upgrade sheaf-ai` for security patches

## Data Handling

- Article URLs are logged in your local index (never sent to us)
- Article content is fetched client-side (never proxied through our servers)
- LLM prompts include article content + system instructions (sent only to your configured provider)
