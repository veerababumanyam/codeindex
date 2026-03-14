---
phase: 01
plan_id: 02-PLAN
title: Root-Bound Analysis and Safe Memory Rendering
wave: 1
depends_on: []
files_modified:
  - codeindex/analysis.py
  - codeindex/server.py
  - codeindex/memory_viewer.py
  - tests/test_server.py
autonomous: true
requirements:
  - SEC-03
  - SEC-04
---

# Phase 1 Plan 02: Root-Bound Analysis and Safe Memory Rendering

<goal>
Prevent server-driven file analysis from escaping the configured project boundary and ensure memory-derived viewer content is rendered as inert text.
</goal>

<must_haves>
- Server-side analysis always uses the canonical configured project root.
- Caller-supplied analysis inputs cannot escape the allowed root via override, traversal, or absolute path tricks.
- Boundary failures return clear client-facing errors instead of silently reading arbitrary files.
- Memory viewer output never trusts memory-derived HTML and uses safe text rendering for both page and stream presentation.
</must_haves>

<scope>
- Remove or neutralize caller control over server analysis roots in `codeindex/server.py`.
- Add defense-in-depth root boundary validation in `codeindex/analysis.py`.
- Replace unsafe viewer DOM injection patterns in `codeindex/memory_viewer.py`.
- Add endpoint tests for analysis boundary rejection and viewer safety regression coverage.
</scope>

<tasks>
  <task id="1-02-01" requirement="SEC-03">
    <objective>Canonicalize server analysis around one trusted root.</objective>
    <implementation>
      - Update server analysis request handling so HTTP and MCP paths derive their root from the configured workspace/project root only.
      - Reject or ignore caller-provided root overrides; if accepted for compatibility, they must not change the effective root.
      - Reject absolute paths and path traversal attempts before analysis execution.
    </implementation>
    <files>codeindex/server.py, tests/test_server.py</files>
    <verification>
      - `pytest tests/test_server.py -q -k analysis`
      - Tests cover outside-root overrides, traversal attempts, and absolute-path rejection.
    </verification>
  </task>

  <task id="1-02-02" requirement="SEC-03">
    <objective>Add analysis-layer boundary checks so resolved files cannot escape the trusted root.</objective>
    <implementation>
      - Harden file resolution helpers in `codeindex/analysis.py` with canonical path comparison against the provided root.
      - Ensure helper behavior is deterministic for symlink-free and normalized path cases used by current tests.
      - Keep CLI-local analysis behavior unchanged aside from the stronger boundary guarantee when a root is supplied.
    </implementation>
    <files>codeindex/analysis.py, tests/test_server.py</files>
    <verification>
      - `pytest tests/test_server.py -q -k analysis`
      - Add coverage that proves server-side requests cannot read files outside the allowed project even if lower-level helpers are reached.
    </verification>
  </task>

  <task id="1-02-03" requirement="SEC-04">
    <objective>Render untrusted memory content as plain text in the viewer.</objective>
    <implementation>
      - Replace `innerHTML`-style rendering of memory-derived fields with DOM node creation plus `textContent` assignment.
      - Apply the same safe rendering pattern to result cards and stream-fed cards.
      - Preserve existing layout and metadata visibility while removing executable markup injection paths.
    </implementation>
    <files>codeindex/memory_viewer.py, tests/test_server.py</files>
    <verification>
      - `pytest tests/test_server.py -q -k viewer`
      - Insert attacker-controlled markup in memory content and assert it is rendered as literal text, not executable HTML.
    </verification>
  </task>
</tasks>

<execution_order>
- Update server analysis request handling before hardening lower-level analysis helpers so endpoint behavior is defined first.
- Complete viewer rendering changes after boundary work or in parallel if ownership is isolated.
- Consolidate endpoint regression tests after implementation so one server test module verifies all negative cases together.
</execution_order>

<acceptance_criteria>
- HTTP and MCP analysis requests cannot switch to an arbitrary root outside the configured project.
- Absolute-path and traversal inputs receive clear failure responses.
- Lower-level analysis helpers reject paths that resolve outside the trusted root.
- Memory viewer pages and event-driven cards display untrusted markup as text and do not inject executable HTML.
- Existing non-security viewer behavior remains readable and structurally intact.
</acceptance_criteria>

<handoff>
This plan completes the remaining Phase 1 hardening scope. After both wave 1 plans execute, the phase should be ready for consolidated validation against SEC-01 through SEC-04 using the existing `01-VALIDATION.md` contract.
</handoff>
