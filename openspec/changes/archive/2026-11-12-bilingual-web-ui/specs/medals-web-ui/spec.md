# Spec Delta

## MODIFIED Requirements

### Requirement: Medal standings page
The system SHALL serve an English-language medal standings page by default via `GET /` with a table and exactly two filters: year and challenge type. The page and its resources MUST be available from the same application when running locally and in Docker, without a separate frontend server or external CDNs. Existing REST API endpoints, `/docs`, `/openapi.json`, and `/health` MUST remain available.

#### Scenario: First visit
- **WHEN** a visitor opens `/`
- **THEN** they see the heading “Medal standings”, the filters “Year” and “Challenge type”, the selected values “All time” and “All types”, and, after loading, the corresponding standings

#### Scenario: Docker installation
- **WHEN** the application runs from a built Docker image
- **THEN** `/`, CSS, and JavaScript are available at the same address and port as the REST API, and `/docs` and `/health` continue to work

### Requirement: Dynamic year filter
The year filter SHALL contain “All time” first, followed by unique end years of saved challenges in UTC in descending order. The list MUST be built from current data on page load, without a fixed range or years absent from the data. The list SHALL be shared across all challenge types and MUST NOT change when the type changes. The selected calendar year SHALL limit the standings to end dates from January 1 through December 31 inclusive in UTC. “All time” SHALL remove the date restriction while retaining the selected type.

#### Scenario: Nonsequential years
- **WHEN** the database contains challenges that ended only in 2026 and 2024
- **THEN** the filter shows “All time”, “2026”, “2024”, without 2025 or duplicates

#### Scenario: End year
- **WHEN** “2025” is selected and a challenge started in 2024 and ended in 2025
- **THEN** its medals are included in the 2025 standings

#### Scenario: New data
- **WHEN** a challenge with a new end year is saved and the visitor reopens the page
- **THEN** the new year appears in the filter without code changes or rebuilding the UI

#### Scenario: Changing the type retains the year
- **WHEN** the visitor selects 2025 and then “Team”
- **THEN** 2025 remains selected and the year list does not change

### Requirement: Type filter and combined application
The type filter SHALL contain “All types”, “Team”, “Project”. Both filters SHALL be applied together. Changing either filter SHALL update the standings without a full page reload or an additional apply button. During rapid changes, the result MUST correspond to the latest selection, even if responses arrive out of order.

#### Scenario: Filter combination
- **WHEN** “2025” and “Project” are selected
- **THEN** the table shows medals only from project challenges that ended in 2025

#### Scenario: All time for the selected type
- **WHEN** “All time” and “Team” are selected
- **THEN** the table shows team challenge medals for all available years

#### Scenario: Stale response
- **WHEN** the response to a request for the previous selection arrives after the response for the current one
- **THEN** the table and page status remain consistent with the current selection

### Requirement: Medal table
The table SHALL show one row per team with at least one medal in the selected data set and the columns “Team”, “Gold”, “Silver”, “Bronze”, “Total”. Counts SHALL match the REST API, including ties and zeros for individual medal types. The order SHALL be Olympic: gold, silver, bronze descending, then team name ascending; the total count MUST NOT replace this sorting. Team names MUST be displayed exactly as in the data, as text, without executing HTML.

#### Scenario: Olympic order
- **WHEN** A has 2 gold medals and B has 1 gold and 5 silver medals
- **THEN** A appears above B despite having fewer medals in total

#### Scenario: Tie and zero values
- **WHEN** two teams receive silver in one challenge and one has no gold
- **THEN** both are credited with silver, and the absence of gold is displayed as the number 0

#### Scenario: Name with markup
- **WHEN** a team name contains HTML markup characters
- **THEN** the name is displayed as literal text, without adding HTML elements or executing scripts

### Requirement: Loading, empty result, and error states
The page SHALL distinguish loading, a successfully loaded empty data set, and a data retrieval error. During an update, rows from the previous data set MUST NOT be shown as the result of the current filters. On error, a clear message and a “Retry” button that preserves the current filters SHALL be displayed. A failure to load the year list MUST NOT be replaced with a “no challenges” message. Errors and retries MUST NOT require a full page reload.

#### Scenario: Waiting
- **WHEN** loading of the standings for new filters starts
- **THEN** the page reports “Loading…” and does not present the previous rows as current

#### Scenario: No data for the combination
- **WHEN** successfully loaded standings for the selected year and type are empty
- **THEN** “No medals for the selected period and challenge type” is shown, and the filters remain available

#### Scenario: Empty database
- **WHEN** the year list and medal standings are successfully loaded from an empty database
- **THEN** the year filter contains only “All time”, the table is empty, and a message about the absence of medals is shown

#### Scenario: API error and recovery
- **WHEN** a year list or standings request fails with a network error or unsuccessful HTTP status and the visitor then clicks “Retry”
- **THEN** an error is shown until the retry, the current selection is preserved, and the corresponding content is restored after a successful response

### Requirement: Accessibility and narrow screens
Filters and retry SHALL have visible labels and work with the keyboard. The table SHALL have semantic headers; loading/error status SHALL be accessible to assistive technologies. On a 360 px wide screen, filters and text MUST remain readable; horizontal scrolling SHALL be limited to the table if needed. The medal type MUST be distinguishable by text, rather than color alone.

#### Scenario: Keyboard control
- **WHEN** a visitor uses Tab and selection keys
- **THEN** they can change both filters and retry, with visible focus

#### Scenario: Phone and long names
- **WHEN** the page is opened on a 360 px wide screen with long team names
- **THEN** filters are accessible, medal values are readable, and the table does not cause horizontal scrolling of the entire page

## ADDED Requirements

### Requirement: Interface language selection
The page SHALL offer English and Russian through a visible, keyboard-accessible language selector. English SHALL be selected on a first visit regardless of browser language. A supported explicit choice SHALL be restored on later visits when local browser storage is available; an invalid or unavailable preference SHALL fall back to English without preventing page use. The page SHALL translate all interface content, metadata, accessibility labels, feedback messages, and the team count, and update the document language. Team names MUST remain unchanged. The language selector SHALL be separate from the two standings filters.

#### Scenario: English by default
- **WHEN** a visitor without a saved language choice opens the page using a Russian-language browser
- **THEN** the page and document language are English and the selector offers English and Русский

#### Scenario: Switching language
- **WHEN** a visitor selects Russian while a year and challenge type are selected
- **THEN** all interface text becomes Russian immediately without resetting filters, altering standings, or making additional API requests

#### Scenario: Switching during a request or an error
- **WHEN** the language changes while data are loading or an error is displayed
- **THEN** current feedback and subsequent responses use the selected language, retry remains available after errors, and stale-response protection is preserved

#### Scenario: Saved preference
- **WHEN** a visitor selects Russian and reloads with local storage available
- **THEN** Russian is restored without changing the default for visitors without a saved choice

#### Scenario: Storage unavailable
- **WHEN** browser storage is blocked or contains an unsupported language
- **THEN** the page opens in English and switching languages still works for the current visit
