# Project Specification Template

## Goal
<!-- One paragraph describing what this workflow should accomplish -->
Example: Build a REST API for user management with authentication, CRUD operations, and role-based access control.

## What Already Exists
<!-- Describe any existing code, docs, or infrastructure the agent should know about -->
- Existing source files at: `src/`
- Database schema at: `db/schema.sql`
- DO NOT modify: `config/production.yaml`

## Source / Input Locations
<!-- Where should the agent look for reference material? -->
- Source code: `src/`
- Tests: `tests/`
- Documentation: `docs/`

## Output Requirements
<!-- What files should the agent create or modify? -->
For each task, the agent should:
1. Create/modify source files in `src/`
2. Add tests in `tests/`
3. Update documentation in `docs/`

## Task Categories
<!-- How should the Initializer Agent organize tasks? -->

### Priority 0 (critical) — Foundation
- Project setup, dependencies, configuration

### Priority 1 (high) — Core features
- Authentication, main business logic

### Priority 2 (medium) — Secondary features
- Reporting, notifications, integrations

### Priority 3 (low) — Polish
- Documentation, error handling improvements, performance optimization

## Important Rules
<!-- Constraints the agent must follow -->
1. Each task should be completable in one session (~10-15 minutes)
2. Always write tests for new functionality
3. Follow the existing code style
4. Do not modify files in `vendor/` or `node_modules/`
