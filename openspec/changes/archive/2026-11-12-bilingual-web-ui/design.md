# Design

## Context

The packaged page uses vanilla JavaScript with request cancellation and request IDs. Its HTML and dynamic feedback are Russian-only. API data and team names are independent of interface language.

## Goals / Non-Goals

**Goals:** switch text without reloading data, preserve request state and filters, retain safe text rendering and narrow-screen accessibility.

**Non-Goals:** API localization, translating team names, language detection, external translation services, frontend build tooling.

## Decisions

- Keep English fallback text in HTML and English/Russian dictionaries in the existing app.js. Use data attributes for text and accessible labels; update textContent, never translated HTML. Wrap only text within elements containing icons, links, or line breaks.
- Track feedback by translation key and team count by number so language changes can update current content without clearing rows or starting requests. Async completion uses the current language.
- Use an independent native language select in the header. Set html.lang, document.title, and description when language changes. Preserve selected year/type and server-provided team names.
- Persist only an explicit supported language in localStorage under olympic-language. Catch storage failures and continue with in-memory selection; do not infer language from navigator.language.
- Verify real DOM behavior with a temporary local browser harness and mocked API responses, plus packaged HTTP delivery tests. No new runtime or test dependencies in the project.

## Risks / Trade-offs

- Missing translation keys → compare dictionary key sets and exercise all visible states in both languages.
- A language change clears a loading/error state or standings → retain semantic UI state independently from translated strings and test delayed requests and retries.
- Header overflow at 360 px → compact selector and browser layout checks in both languages.
