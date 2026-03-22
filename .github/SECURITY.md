# Security Policy

## Supported use

`unheard-buzz` is a research toolkit for public social content.
It is not designed for regulated data, private customer data, or sensitive internal analytics.

## Reporting a vulnerability

If you discover a security issue, please do not open a public issue with exploit details.

Instead:

1. Email the maintainer privately.
2. Include reproduction steps, impact, and any suggested mitigation.
3. Allow time for a fix before public disclosure.

If no private contact channel is listed yet, open a minimal public issue requesting a security contact without including exploit details.

## Secret-handling expectations

- Never commit `.env` files, API keys, tokens, or private exports
- Treat `input/` CSV files as local-only unless they are explicitly sanitized samples
- Review generated reports before sharing them publicly
