---
name: "maltego-transform-design"
description: "Load this skill when designing transforms for a data source: entity modeling, transform sets, input constraints, settings, pagination, and investigator workflows."
metadata:
  version: "1.0.0"
---

# Maltego Transform Design Skill

## Purpose
Guide agents through designing Maltego transforms for a data source before writing any code. Produce a clear design covering entities, transform sets, settings, and investigator workflows.

## Step-by-Step Design Process

### 1. Understand the Data Source
- What objects does the API return? (domains, IPs, people, events, etc.)
- What are the natural investigative pivots? (e.g., domain → IPs, IP → domains, email → person)
- What parameters does the API require? (API keys, search terms, pagination tokens)

### 2. Map to Standard Entities FIRST
**Always check `maltego-transforms-std-entities` before inventing custom entities.**

- Load `references/standard-entity-selection.md` for entity categories, import patterns, and selection guidance.
- Import from `maltego.entities` (e.g., `from maltego.entities import Domain, Person, IPv4Address`). These classes ship in the `maltego-transforms-std-entities` package.
- If a standard entity class fits — use it. Do not create a custom entity for the sake of it.

### 3. Propose Custom Entities Only When Needed
Custom entities are justified only when:
- No standard entity class matches the concept.
- The data has meaningful properties that standard entities cannot carry.
- The entity would genuinely be pivoted on in investigations (not just a data container).

Document proposed custom entities with: name, display name, properties, and why no standard entity fits.

### 4. Design Transform Sets
Group transforms by investigative flow:
- Name each transform set by its input → output concept (e.g., "Domain Enrichment", "Person Lookup").
- Each transform set = one input entity type → one or more output entity types.
- The input and output entity types you design here must be reflected in each transform's
  type annotations (first parameter for input; return annotation for output, using a union
  when a transform emits more than one type) — those annotations are what `/api/v3/transforms`
  publishes and what the client routes on.
- Identify which transforms are independent vs. chained.

### 5. Design Settings
Determine what configuration the transforms need:
- **Server-level settings**: API keys, base URLs, timeout values (same for all transforms).
- **Per-transform settings**: result limits, toggles, optional filters (per-transform overrides).

### 6. Design Input Constraints
Specify which entity values the transform should accept:
- Regex patterns for domains, IPs, emails.
- Enum constraints for fixed value sets.
- Document any values that should be rejected up front.

### 7. Design Pagination
If the API returns large result sets:
- Decide on page size and pass page tokens via transform settings.
- For offset/page-number APIs: store the page number in a transform setting and increment it each run.
- For cursor/token-based APIs: the cursor cannot be incremented numerically — thread it back via an entity property (e.g. a `next_cursor` field on a result entity) or a per-run transform setting. Do not guess or compute the next cursor.
- Document the pagination strategy in the design.

### 8. Document Investigator Workflows
Write a short investigative workflow for each transform set:
- Starting entity type → transforms to run → what the investigator sees next.
- This becomes the basis for testing and documentation.

## Routing

- **API/entity schema questions**: load `maltego-transform-docs` to look up docs.
- **Common transform mechanics**: load `maltego-transform-basics`.
- **Implementation workflow (how to write the code)**: load `maltego-transform-build`.
- **Entity selection details**: load `references/standard-entity-selection.md` from this skill.

## What NOT to Do

- Do NOT create custom entities before checking standard ones.
- Do NOT start writing transform code during design — that belongs in `maltego-transform-build`.
- Do NOT assume proprietary deployment infrastructure.
- Do NOT model transforms around internal tooling or internal auth systems.
