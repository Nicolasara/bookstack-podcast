# Security Policy

## Reporting a vulnerability

If you discover a security vulnerability in BookStack Podcast, please **do not open a public issue**. Instead, email the details to:

**nicoaraujo2002@gmail.com**

Include:

- A description of the vulnerability
- Steps to reproduce
- The affected version
- Any potential impact

You should receive a response within a few days. Once the issue is confirmed and patched, a security advisory will be published.

## Scope

In-scope:

- Authentication / authorization issues
- Remote code execution
- Data exposure (API keys, episode content)
- SSRF, CSRF, XSS in the web UI
- Path traversal in the audio file serving endpoint

Out-of-scope:

- Issues requiring a malicious BookStack admin
- Self-XSS via deliberate browser console actions
- Vulnerabilities in third-party dependencies that don't affect this project's actual usage (please report those upstream)
- The fact that the service has no built-in authentication (this is documented — run it behind a reverse proxy with auth if exposed publicly)

## Security considerations for operators

This service is designed to be run on a trusted network or behind authentication. By default it has:

- **No built-in authentication** — anyone with network access can use it
- **Permissive CORS** — `allow_origins=["*"]` to support the BookStack hack
- **Plaintext API key storage** — keys are stored unencrypted in `data/settings.json`

For public deployments, run it behind a reverse proxy with authentication (Caddy with basic auth, Authelia, Authentik, etc.) and restrict network access.
