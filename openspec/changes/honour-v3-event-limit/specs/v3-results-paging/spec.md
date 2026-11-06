## Purpose

A V3 results page returns the events a client asks for, bounded by the
server's maximum page size.

## ADDED Requirements

### Requirement: A results page honours the client's eventLimit up to v3_page_size_max

The results endpoints MUST return up to `eventLimit` events from
`eventPointer`, capped at `v3_page_size_max`. The default
`v3_page_size_max` MUST be 10,000. A request without `eventLimit`, or with
`eventLimit <= 0`, MUST return up to 50 events, or up to
`v3_page_size_max` when that is lower.

#### Scenario: A client asks for the rest of the run in one page
- **WHEN** a completed run has 240 events, the client has read 50, and it
  requests `eventPointer=50&eventLimit=190`
- **THEN** the page holds the remaining 190 events.

#### Scenario: A request without eventLimit keeps the default page
- **WHEN** a client requests the results of a 240-event run without
  `eventLimit`
- **THEN** the page holds 50 events.

#### Scenario: The maximum caps every page
- **WHEN** `v3_page_size_max` is 100 and a client requests `eventLimit=1000`
- **THEN** the page holds 100 events, and a request without `eventLimit`
  holds 50.
- **WHEN** `v3_page_size_max` is 20
- **THEN** both requests return 20 events.
