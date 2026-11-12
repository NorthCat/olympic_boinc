# page-fetching Specification

## Purpose

Fetching BoincStats HTML pages for subsequent parsing. Fetching must pass Cloudflare protection, avoid overloading the site, and explicitly report when a page could not be fetched.

## Requirements

### Requirement: Fetching page HTML
The system SHALL return the HTML content of the page containing data for a BoincStats page URL. A placeholder page (a Cloudflare check or BoincStats' own CAPTCHA) MUST NOT be returned as a successful result.

#### Scenario: Successful fetch
- **WHEN** an available BoincStats page is requested
- **THEN** the HTML of the page containing data is returned

#### Scenario: Cloudflare challenge page received
- **WHEN** the response is a Cloudflare check page (for example, “Just a moment…”) or a 403 from Cloudflare
- **THEN** fetching fails with a “blocked” error that is distinct from other fetch errors

#### Scenario: BoincStats CAPTCHA received
- **WHEN** the response is a BoincStats firewall CAPTCHA page (“Please solve Captcha”), with any HTTP status
- **THEN** fetching immediately fails with a “blocked” error, without retries

### Requirement: Request rate limiting
The system SHALL wait between consecutive requests to BoincStats. The delay is configurable and defaults to at least 1 second.

#### Scenario: Series of requests
- **WHEN** several pages are requested consecutively
- **THEN** the time between the starts of adjacent requests is at least the configured delay

### Requirement: Retries for temporary errors
The system SHALL retry a request on network errors, timeouts, and 5xx and 429 responses. The number of retries does not exceed the configured number (3 by default), and the delay between them increases. 4xx errors other than 429 MUST NOT be retried.

#### Scenario: Temporary failure
- **WHEN** the first request times out and the second succeeds
- **THEN** the HTML from the second request is returned

#### Scenario: Retries exhausted
- **WHEN** all attempts fail with a 5xx error
- **THEN** fetching fails with an error that includes the URL and the last status

#### Scenario: Page not found
- **WHEN** the server responds with 404
- **THEN** fetching immediately fails, without retries

### Requirement: Replaceable fetching method
The system SHALL fetch pages through a browser that passes the Cloudflare check. The fetching method MUST be isolated behind a common interface: parsing and synchronization components depend only on the interface, rather than a specific implementation.

#### Scenario: Replacing the implementation
- **WHEN** the fetching implementation is replaced with another one (for example, a fake that returns saved pages)
- **THEN** parsing and synchronization components work without changes
