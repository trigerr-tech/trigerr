# Security Policy

## Supported versions

Security fixes are applied to the latest released version of Trigerr.

## Reporting a vulnerability

Please do not open a public issue for a suspected vulnerability. Use the
repository's private vulnerability-reporting feature when it is enabled, or
contact the project maintainer through the contact method listed on the GitHub
repository.

Include the affected version, a clear reproduction, impact, and any suggested
mitigation. Do not include credentials, API keys, or account information.

## Handling secrets

Never commit API keys, broker credentials, database connection strings, or
production endpoints. Use environment variables or an untracked local
configuration file when an integration requires them.
