# Codex Result Schema

## Goal

Define the strict JSON schema accepted from Codex before any decision can be stored.

## Implementation Scope

TBD from design docs before implementation. This milestone should implement Pydantic result models and enums for decision, confidence, test result, and evidence type.

## Expected Behavior

- Valid `output/codex_result.json` parses successfully.
- Malformed JSON or unknown enum values fail validation.
- Required generic fields are enforced.

## Affected Modules or Commands

- `backport_harness/codex_result.py`
- Tests for valid and invalid result examples

## Test Plan

TBD. At minimum, cover valid result, malformed result, missing required fields, unknown decision, unknown confidence, and representative evidence payloads.

## Assumptions and Explicit Non-goals

- Do not implement this milestone until the task is expanded and checked against the design docs.
- This milestone validates schema shape only; decision-specific evidence validation is separate.

