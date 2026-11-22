# Security Policy

FirmAlways Gate is a privacy tool, so we treat any way to get personal data past it as a security issue.

## Reporting a vulnerability

Please **do not open a public issue** for a vulnerability. Use GitHub's private reporting:
**Security → Report a vulnerability** on https://github.com/firmalways/gate.

Include the Gate version, your policy (with secrets removed), and a minimal input that reproduces the problem. Use **synthetic data only**: never send real personal data, real keys or real customer content in a report.

We aim to acknowledge reports within 3 business days and to agree on a fix and disclosure date with you. We credit reporters who want to be credited.

## What counts as a vulnerability

- Personal data or a secret reaching an upstream although the policy says `mask` or `block`
- Gate forwarding a request after an inspection error (it must fail closed)
- Prompt, answer, placeholder mapping or raw values written to the audit log or server log
- Bypassing client authentication, the model allowlist or the request size limit
- A crafted input that crashes Gate or makes detection take excessive time (ReDoS)
- Placeholder restoration putting one request's values into another request's answer

## Not a vulnerability (but please open a normal issue)

- A detector missing a format it does not claim to support, or a false positive. These are accuracy bugs; see "Known limits" in the README.
- Data leaking through traffic that does not pass through Gate.
- Context that remains after masking (masking a name does not hide the rest of the sentence).

## Supported versions

Only the latest release on `main` receives security fixes during the 0.x series.

## Deployment guidance

- Keep Gate on `127.0.0.1` or a private network, put TLS in front of it, and set `FIRMALWAYS_GATE_API_KEY` (or per-client keys) whenever it is reachable by more than one machine.
- Keep provider keys only in Gate's environment.
- Set `FIRMALWAYS_AUDIT_HMAC_KEY` if audit records must not contain user identifiers in clear text, and protect the audit file like any other log.
- Gate supports PDPA work; it does not by itself make an organization compliant.
