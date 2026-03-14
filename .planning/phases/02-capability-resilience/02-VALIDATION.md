---
phase: 02
slug: capability-resilience
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-14
---

# Phase 02 - Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `python -m pytest tests/test_memory_storage.py tests/test_cli.py tests/test_server.py -q -k "status or memory or query or fts"` |
| **Full suite command** | `python -m pytest -q` |
| **Estimated runtime** | ~20 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_memory_storage.py tests/test_cli.py tests/test_server.py -q -k "status or memory or query or fts"`
- **After every plan wave:** Run `python -m pytest -q`
- **Before `$gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | CAP-01 | packaging+integration | `python -m pip install -e .` and `python -m pytest tests/test_cli.py tests/test_server.py -q -k "query or status"` | yes | pending |
| 02-01-02 | 01 | 1 | CAP-02 | unit+integration | `python -m pytest tests/test_memory_storage.py tests/test_cli.py tests/test_server.py -q -k "memory or fts"` | yes | pending |
| 02-01-03 | 01 | 1 | CAP-03 | integration | `python -m pytest tests/test_cli.py tests/test_server.py -q -k "status or memory_status"` | yes | pending |

*Status: pending | green | red | flaky*

---

## Wave 0 Requirements

- Existing infrastructure covers all phase requirements.
- `tests/test_memory_storage.py` will be added for no-FTS storage assertions.

---

## Manual-Only Verifications

- All phase behaviors have automated verification.

---

## Validation Sign-Off

- [x] All tasks have automated verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all missing references
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
