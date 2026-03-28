# youtrack-qa-agent

An AI-powered QA agent for the Real Brokerage bolt platform. Give it a YouTrack ticket ID and it automatically:
- Fetches the ticket details
- Finds relevant source files in the bolt repo
- Generates a REST Assured Java test class
- Generates a Postman collection
- Applies the actual bug fix code to bolt source files
- Raises GitHub PRs in both repos — only after your approval

---

## Table of Contents

- [How it works](#how-it-works)
- [Prerequisites](#prerequisites)
- [Step 1 — Clone the repos](#step-1--clone-the-repos)
- [Step 2 — Install Python dependencies](#step-2--install-python-dependencies)
- [Step 3 — Get your API tokens](#step-3--get-your-api-tokens)
- [Step 4 — Configure your shell](#step-4--configure-your-shell)
- [Step 5 — Run the agent](#step-5--run-the-agent)
- [Flags reference](#flags-reference)
- [Outputs](#outputs)
- [PR approval flow](#pr-approval-flow)
- [How bug fix code works](#how-bug-fix-code-works)
- [Supported environments](#supported-environments)
- [Supported services](#supported-services)
- [Project structure](#project-structure)
- [Troubleshooting](#troubleshooting)

---

## How it works

```
qa RV2-64044 --env team2 --pr
```

1. **Fetch ticket** — pulls summary, description, type, priority, state, and custom fields from YouTrack
2. **Find source files** — searches `~/bolt/src` for TypeScript/React files relevant to the ticket keywords (modal, coordinator, team, etc.)
3. **Ask Claude** — sends ticket + source file contents to Claude AI (claude-opus-4-6)
4. **Generate REST Assured test** — a complete Java test class that reproduces the bug (fails before fix, passes after) or covers the new story feature
5. **Generate Postman collection** — ready-to-import JSON collection for manual verification
6. **Apply bug fix** — Claude outputs exact code changes; the tool patches the real files in `~/bolt/src/`
7. **PR preview** — shows you exactly what will be committed and pushed, then waits for `y/N`
8. **Raise PRs** — pushes branches and creates PRs in `Realtyka/bolt` (fix) and `manepranal/bolt-rest-assured` (tests)

---

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.9+ | Check: `python3 --version` |
| pip | any | Check: `pip3 --version` |
| git | any | Check: `git --version` |
| `~/bolt` repo | — | bolt frontend cloned locally |
| `~/bolt-rest-assured` repo | — | REST Assured test repo cloned locally |

---

## Step 1 — Clone the repos

You need both bolt repos cloned to your home directory:

```bash
# bolt frontend (if not already cloned)
git clone https://github.com/Realtyka/bolt.git ~/bolt

# REST Assured test suite
git clone https://github.com/manepranal/bolt-rest-assured.git ~/bolt-rest-assured

# This agent
git clone https://github.com/manepranal/youtrack-qa-agent.git ~/youtrack-qa-agent
```

---

## Step 2 — Install Python dependencies

```bash
pip3 install -r ~/youtrack-qa-agent/requirements.txt
```

This installs:
- `anthropic` — Claude AI SDK
- `requests` — HTTP client for YouTrack + GitHub APIs

---

## Step 3 — Get your API tokens

You need three tokens. Here's where to get each one:

### Anthropic API Key (`ANTHROPIC_API_KEY`)
1. Go to [console.anthropic.com](https://console.anthropic.com)
2. Sign in or create an account
3. Click **API Keys** in the left sidebar
4. Click **Create Key** → copy it (starts with `sk-ant-`)

### YouTrack Token (`YOUTRACK_TOKEN`)
1. Go to [realbrokerage.youtrack.cloud](https://realbrokerage.youtrack.cloud)
2. Click your profile picture → **Profile**
3. Go to the **Auth tokens** tab
4. Click **New token** → give it a name (e.g. `qa-agent`) → copy it (starts with `perm-`)

### GitHub Token (`GITHUB_TOKEN`) — only needed for `--pr`
1. Go to [github.com/settings/tokens](https://github.com/settings/tokens)
2. Click **Generate new token (classic)**
3. Give it a name (e.g. `qa-agent`), set expiry, tick the **repo** scope
4. Click **Generate token** → copy it (starts with `ghp_`)

---

## Step 4 — Configure your shell

Add the following to your `~/.zshrc` (or `~/.bashrc`):

```bash
# YouTrack QA Agent
export ANTHROPIC_API_KEY="sk-ant-your-key-here"
export YOUTRACK_TOKEN="perm-your-token-here"
export GITHUB_TOKEN="ghp_your-token-here"
alias qa="python3 $HOME/youtrack-qa-agent/youtrack_qa.py"
```

Then reload your shell:
```bash
source ~/.zshrc
```

---

## Step 5 — Run the agent

### Basic — generate tests and fix only (no PR)
```bash
qa RV2-64044 --env team2
```

### Full — generate + raise PRs with approval
```bash
qa RV2-64044 --env team2 --pr
```

### Other examples
```bash
# Staging environment
qa RV2-62364 --env staging --pr

# team3 with a custom base branch
qa RV2-64044 --env team3 --pr --base develop

# Override YouTrack token inline
qa RV2-64044 --env team1 --yt-token perm-xxx
```

---

## Flags reference

| Flag | Default | Description |
|------|---------|-------------|
| `ticket_id` | required | YouTrack ticket ID, e.g. `RV2-64044` |
| `--env` | `team1` | Target environment: `team1` `team2` `team3` `team4` `staging` `play` |
| `--pr` | off | Create branches + raise GitHub PRs (requires `GITHUB_TOKEN`) |
| `--base` | auto-detected | Base branch for the PR (e.g. `main`, `develop`) |
| `--yt-token` | `$YOUTRACK_TOKEN` | Override YouTrack token for this run |

---

## Outputs

| Artifact | Where it goes |
|----------|--------------|
| REST Assured test `.java` | `~/bolt-rest-assured/src/test/java/com/real/api/<TicketId>Test.java` |
| Postman collection `.json` | `~/bolt/postman/collections/<TICKET_ID>.postman_collection.json` |
| Bug fix code | Applied directly to the relevant file(s) in `~/bolt/src/` |
| PR — bolt | `Realtyka/bolt` — branch `qa/<ticket-id>`, contains fix + Postman collection |
| PR — tests | `manepranal/bolt-rest-assured` — branch `qa/<ticket-id>`, contains Java test |

---

## PR approval flow

When `--pr` is passed, the tool always shows a preview and waits for your input before pushing anything:

```
============================================================
PR PREVIEW — Review before raising
============================================================

[1] Realtyka/bolt
    Branch : qa/rv2-64044  →  main
    Title  : QA: RV2-64044 — Bolt: When Leader click on view...
    Files  :
      • src/components/TransactionCoordinator/Teams/ViewModal.tsx
      • postman/collections/RV2_64044.postman_collection.json

    Fix summary:
      The modal was not rendered because the visibility state was never
      set to true on the Leader "view" button click handler...

[2] manepranal/bolt-rest-assured
    Branch : qa/rv2-64044  →  main
    Files  :
      • RV264044Test.java

============================================================
Raise PR(s)? [y/N]:
```

- Type `y` → branches are pushed and PRs are created
- Type `N` or press Enter → nothing is pushed, changes stay local on the branch

---

## How bug fix code works

Claude outputs fix code in a structured diff format:

```
FILE: src/components/TransactionCoordinator/Teams/ViewModal.tsx
<<<<<<< ORIGINAL
(exact original lines from the file)
=======
(corrected replacement lines)
>>>>>>> FIXED
```

The tool reads the actual file, finds the original lines, and replaces them with the fixed version. If the original lines are not found exactly (e.g. Claude paraphrased), it will print a warning and skip that file — you'll need to apply it manually.

---

## Supported environments

| Env | Bolt App | Service API pattern |
|-----|----------|-------------------|
| team1 | `https://bolt.team1realbrokerage.com` | `https://{service}.team1realbrokerage.com` |
| team2 | `https://bolt.team2realbrokerage.com` | `https://{service}.team2realbrokerage.com` |
| team3 | `https://bolt.team3realbrokerage.com` | `https://{service}.team3realbrokerage.com` |
| team4 | `https://bolt.team4realbrokerage.com` | `https://{service}.team4realbrokerage.com` |
| staging | `https://bolt.stagerealbrokerage.com` | `https://{service}.stagerealbrokerage.com` |
| play | `https://bolt.playrealbrokerage.com` | `https://{service}.playrealbrokerage.com` |

---

## Supported services

The agent knows about all bolt microservices and maps them to the right base URLs:

`arrakis` · `keymaker` · `yenta` · `hermes` · `wallet` · `leo` · `mufasa` · `wanderer` · `sherlock` · `yada` · `memento` · `bff` · `dropbox` · `avalon` · `mercury` · `atlantis` · `signature-api` · `plutus` · `insignia` · `sirius` · `hawkeye` · `yenta-worker`

---

## Project structure

```
youtrack-qa-agent/
├── youtrack_qa.py       # Main agent script
├── requirements.txt     # Python dependencies (anthropic, requests)
├── .gitignore
└── README.md
```

### What's inside `youtrack_qa.py`

| Section | What it does |
|---------|-------------|
| `fetch_ticket()` | Calls YouTrack REST API to get ticket details |
| `ticket_summary()` | Formats ticket data into a readable string for Claude |
| `find_relevant_files()` | Greps bolt/src for files matching ticket keywords |
| `generate_artifacts()` | Sends ticket + source to Claude, gets back all four sections |
| `parse_sections()` | Splits Claude's response into REST Assured / Postman / fix code / explanation |
| `save_rest_assured()` | Writes the Java test class to bolt-rest-assured |
| `save_postman()` | Writes the Postman collection JSON to bolt/postman/collections |
| `apply_fix_code()` | Parses the diff blocks and patches actual files in bolt/src |
| `pr_flow()` | Shows preview, waits for approval, creates branches, pushes, calls GitHub API |
| `github_create_pr()` | Creates a PR via GitHub REST API |

---

## Troubleshooting

### `ANTHROPIC_API_KEY not set`
```bash
export ANTHROPIC_API_KEY=sk-ant-your-key
```

### `YOUTRACK_TOKEN not set`
```bash
export YOUTRACK_TOKEN=perm-your-token
```

### `Ticket not found in YouTrack`
Make sure the ticket ID is correct and your YouTrack token has read access to the project.

### `WARNING: Original code not found in file — skipping apply`
Claude generated a fix but the exact lines didn't match the current file. This can happen if the file was recently changed. Review the fix manually from the terminal output and apply it yourself.

### `--pr requires GITHUB_TOKEN`
```bash
export GITHUB_TOKEN=ghp_your-token
```
Make sure the token has the **repo** scope.

### PR already exists
The tool detects this and prints the existing PR URL instead of failing.
