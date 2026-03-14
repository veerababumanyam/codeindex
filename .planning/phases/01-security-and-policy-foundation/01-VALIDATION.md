---
phase: 01
slug: security-and-policy-foundation
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2026-03-14
---

# Phase 01 - Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `pytest tests/test_cli.py tests/test_server.py -q` |
| **Full suite command** | `pytest -q` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_cli.py tests/test_server.py -q`
- **After every plan wave:** Run `pytest -q`
- **Before `$gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 1-01-01 | 01 | 1 | SEC-01 | unit | `pytest tests/test_cli.py -q` | yes | pending |
| 1-01-02 | 01 | 1 | SEC-01 | integration | `pytest tests/test_server.py -q -k remote` | W0 | pending |
| 1-01-03 | 01 | 1 | SEC-02 | integration | `pytest tests/test_server.py -q -k auth` | W0 | pending |
| 1-01-04 | 01 | 1 | SEC-01 | unit | `pytest tests/test_cli.py -q` | yes | pending |
| 1-02-01 | 02 | 1 | SEC-03 | integration | `pytest tests/test_server.py -q -k analysis` | W0 | pending |
| 1-02-02 | 02 | 1 | SEC-03 | integration | `pytest tests/test_server.py -q -k analysis` | W0 | pending |
| 1-02-03 | 02 | 1 | SEC-04 | integration | `pytest tests/test_server.py -q -k viewer` | W0 | pending |
| 1-01-RG | 01 | 2 | SEC-01, SEC-02 | regression | `pytest -q` | yes | pending |
| 1-02-RG | 02 | 2 | SEC-03, SEC-04 | regression | `pytest -q` | yes | pending |

*Status: pending | green | red | flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_server.py` - add remote-host policy coverage
- [ ] `tests/test_server.py` - add token-auth coverage for HTTP and MCP
- [ ] `tests/test_server.py` - add analysis root/path rejection coverage
- [ ] `tests/test_server.py` - add safe viewer rendering coverage
- [ ] `tests/test_cli.py` - add server config/flag validation coverage for remote and auth settings

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Remote startup error wording stays clear for operators | SEC-01 | Exact UX wording is easier to judge manually than by brittle string matching | Start with `codeindex serve --host 0.0.0.0` without opt-in and confirm the message explains the missing remote-allow step |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-03-14
