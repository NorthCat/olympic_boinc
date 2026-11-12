# Proposal

## Why

The medal standings are currently available only in Russian. Visitors need an English interface by default and a way to switch to Russian.

## What Changes

- Add an accessible English / Русский language selector in the page header.
- Default to English on a first visit and remember an explicitly selected language locally when browser storage is available.
- Translate page content, accessibility labels, metadata, loading/error/empty states, and the team count without reloading data or changing filters.

## Capabilities

### New Capabilities

### Modified Capabilities

- `medals-web-ui`: support English and Russian, with English as the default and language-independent standings behavior.

## Impact

Packaged HTML/CSS/JavaScript, web delivery tests, browser acceptance, and README. REST API contracts, team names, database schema, dependencies, and synchronization are unchanged.
