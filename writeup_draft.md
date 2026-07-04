# KAGE — Autonomous Dependency Vulnerability Triage Agent

*Draft for the Kaggle writeup. Trim/adjust in your own voice before posting —
this is scaffolding, not a script to paste verbatim.*

## What it is

KAGE is an agent that takes a project's dependency manifest
(`requirements.txt` or `package.json`) and autonomously investigates whether
any of those packages have known security vulnerabilities — then produces a
prioritized, plain-English remediation report instead of a raw CVE dump.

## Rationale

Dependency vulnerabilities are one of the most common and most ignored
attack surfaces in software — most developers install packages once and
never revisit them. Tools like `pip-audit` exist but output is a flat list
of CVE IDs with no judgment about what actually needs attention first. I
wanted an agent that does the triage a security engineer would do manually:
gather the facts, then reason about severity and priority, not just report
raw data.

It's also a genuine test of agentic tool orchestration rather than a single
prompt-response loop — the agent decides, turn by turn, whether it needs to
parse a file, query a vulnerability database, or pull details on a specific
CVE, based on what it's already learned.

## How it works

1. **Tool 1 — `parse_dependencies`**: reads the manifest, extracts package
   names/versions
2. **Tool 2 — `check_vulnerabilities`**: batch-queries OSV.dev (Google's
   open vulnerability database) for every package
3. **Tool 3 — `get_vulnerability_details`**: for each hit, pulls CVSS
   severity and a summary
4. The model then writes a final prioritized report — worst risk first,
   with concrete upgrade guidance — and stops calling tools

Built with Google's Agent Development Kit (ADK) 2.0 — the framework taught
in the course. Tools are plain Python functions ADK auto-wraps from their
docstrings; every decision the agent makes is visible as a discrete tool
call, either in the terminal trace or in ADK's built-in `adk web` inspector.

## Code

`<your GitHub repo link here>`

## Video

`<embed/link your demo video here>`

Suggested video structure (2–3 min):
1. 15s — the problem (nobody checks dependencies for CVEs)
2. 30s — architecture: three ADK tools, one LlmAgent, plain Python functions
   auto-wrapped from docstrings
3. 60–90s — live run against `sample_project/requirements.txt`; narrate the
   tool calls as they happen in the terminal (or show `adk web`'s visual
   trace as a second angle)
4. 20s — the final report on screen
5. 15s — one line on how this could extend (CI integration, more ecosystems)
