# Proposal

## Why

All data come from BoincStats pages, but the site is protected by a Cloudflare challenge: regular HTTP clients (curl, requests) receive 403 “Just a moment…”. A reliable way to fetch HTML that is considerate of the site is needed. In addition, real page samples are needed before writing the parser: we have not seen the markup yet.

## What Changes

- Spike: check which method passes Cloudflare. First curl_cffi with browser TLS fingerprint impersonation; if unsuccessful, a browser: Playwright, and after it was blocked, nodriver (Chrome without automation indicators, through CDP).
- Save real pages as test fixtures. Document their structure: columns, date formats, challenge URLs and IDs, pagination.
- A page-fetching component with a replaceable implementation, delay between requests, retries, and blocking detection.
- Browser settings (executable path, sandbox) through configuration.

## Capabilities

### New Capabilities
- `page-fetching`: fetching BoincStats HTML pages while accounting for Cloudflare protection, request rate limiting, and retries on temporary errors.

### Modified Capabilities

## Impact

- New modules: `src/olympic_boinc/scraper/fetcher.py`.
- New files: `tests/fixtures/*.html`.
- Dependencies: tenacity (retries with backoff), opencv-python-headless (for nodriver's `verify_cf` — locating the Cloudflare checkbox in a screenshot), nodriver (requires installed Chrome/Chromium and a display; Xvfb on a server). nodriver does not support Python 3.14, so the project was moved to 3.13.
- Spike results determine the `challenge-parsing` specification.
