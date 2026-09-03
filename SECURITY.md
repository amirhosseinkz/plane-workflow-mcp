# Security Policy

## Supported versions

| Version | Supported |
| --- | --- |
| Current `0.5.x` release line | Yes |
| Older releases | No |

## Reporting a vulnerability

Do not report vulnerabilities through a public issue, discussion, chat, or
pull request. Do not include API keys, access tokens, private URLs, workspace
names, project identifiers, or customer data in a report.

Use GitHub's private vulnerability reporting flow from the repository's
**Security** tab. Maintainers must enable private vulnerability reporting before
making the repository public. If that flow is unavailable, use the private
security contact published in the repository settings.

Include a clear description, affected version, reproduction steps, impact, and
any suggested mitigation. A maintainer will acknowledge the report, assess its
impact, and coordinate a fix before public disclosure where practical.

## Security boundaries

- Store Plane API keys in the operating-system keyring or a secret manager.
- Use environment variables only from trusted deployment or CI secret stores.
- Keep optional bot `.env` files and runtime data local.
- Treat generated work-item reports as potentially sensitive.
- Use least-privilege credentials and restrictive bot allowlists.
