# youtrack-qa-agent

An AI-powered QA agent for the Real Brokerage bolt platform. Give it a YouTrack ticket ID and it automatically generates tests, applies the bug fix, and raises GitHub PRs — all with your approval.

## What does it do?

| Step | What happens |
|------|-------------|
| 1 | Fetches the ticket from YouTrack (summary, description, type, custom fields) |
| 2 | Searches `bolt/src` for source files relevant to the ticket |
| 3 | Sends ticket + source files to Claude (AI) |
| 4 | Generates a **REST Assured Java test class** targeting the right service |
| 5 | Generates a **Postman collection** for manual verification |
| 6 | Generates and **applies actual bug fix code** to the bolt source files |
| 7 | *(with `--pr`)* Shows a full PR preview and waits for your **y/N approval** |
| 8 | *(with `--pr`)* Pushes branches and raises PRs in `Realtyka/bolt` + `manepranal/bolt-rest-assured` |

## Requirements

- Python 3.9+
- `pip install -r requirements.txt`
- Access to `~/bolt` (bolt frontend repo)
- Access to `~/bolt-rest-assured` (REST Assured test repo)

### Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Always | Get from [console.anthropic.com](https://console.anthropic.com) |
| `YOUTRACK_TOKEN` | Always | YouTrack → Profile → Auth Tokens → New token |
| `GITHUB_TOKEN` | Only with `--pr` | GitHub → Settings → Developer settings → Personal access tokens (repo scope) |

Add to `~/.zshrc`:
```bash
export ANTHROPIC_API_KEY=sk-ant-...
export YOUTRACK_TOKEN=perm-...
export GITHUB_TOKEN=ghp_...
alias qa="python3 $HOME/youtrack-qa-agent/youtrack_qa.py"
```

## Installation

```bash
git clone https://github.com/manepranal/youtrack-qa-agent.git ~/youtrack-qa-agent
pip install -r ~/youtrack-qa-agent/requirements.txt
```

Add the alias and env vars above to `~/.zshrc`, then:
```bash
source ~/.zshrc
```

## Usage

```bash
# Generate tests + fix (no PR)
qa RV2-64044 --env team2

# Generate tests + fix + raise PRs (with approval gate)
qa RV2-64044 --env team2 --pr

# Target a different environment
qa RV2-62364 --env staging --pr

# Override base branch
qa RV2-64044 --env team1 --pr --base develop
```

## Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--env` | `team1` | Target environment: `team1`, `team2`, `team3`, `team4`, `staging`, `play` |
| `--pr` | off | Create branches + raise GitHub PRs after approval |
| `--base` | auto-detected | Base branch for PRs |
| `--yt-token` | `$YOUTRACK_TOKEN` | Override YouTrack token inline |

## Outputs

| Artifact | Location |
|----------|----------|
| REST Assured test `.java` | `~/bolt-rest-assured/src/test/java/com/real/api/` |
| Postman collection `.json` | `~/bolt/postman/collections/` |
| Bug fix code | Applied directly to `~/bolt/src/...` |
| PR (bolt) | `Realtyka/bolt` — contains fix code + Postman collection |
| PR (tests) | `manepranal/bolt-rest-assured` — contains the Java test class |

## PR Approval Flow

When `--pr` is passed, the tool shows a full preview before doing anything:

```
============================================================
PR PREVIEW — Review before raising
============================================================

[1] Realtyka/bolt
    Branch : qa/rv2-64044  →  main
    Title  : QA: RV2-64044 — Bolt: When Leader click on view...
    Files  :
      • src/components/TransactionCoordinator/Teams/SomeComponent.tsx
      • postman/collections/RV2_64044.postman_collection.json

    Fix summary: The modal was not being triggered because...

[2] manepranal/bolt-rest-assured
    Branch : qa/rv2-64044  →  main
    Files  :
      • RV264044Test.java

============================================================
Raise PR(s)? [y/N]:
```

Type `y` to push and raise. Type `N` or press Enter to cancel — no changes are pushed.

## Supported Environments

| Env | Bolt App | Service API |
|-----|----------|-------------|
| team1 | `https://bolt.team1realbrokerage.com` | `https://{service}.team1realbrokerage.com` |
| team2 | `https://bolt.team2realbrokerage.com` | `https://{service}.team2realbrokerage.com` |
| team3 | `https://bolt.team3realbrokerage.com` | `https://{service}.team3realbrokerage.com` |
| team4 | `https://bolt.team4realbrokerage.com` | `https://{service}.team4realbrokerage.com` |
| staging | `https://bolt.stagerealbrokerage.com` | `https://{service}.stagerealbrokerage.com` |
| play | `https://bolt.playrealbrokerage.com` | `https://{service}.playrealbrokerage.com` |
