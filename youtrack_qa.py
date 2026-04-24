#!/usr/bin/env python3
"""
YouTrack QA Agent
-----------------
Give it a ticket ID → fetches from YouTrack → uses Claude to generate:
  1. REST Assured Java test class  → ~/bolt-rest-assured/src/test/java/com/real/api/
  2. Postman collection JSON        → ~/bolt/postman/collections/
  3. Actual bug fix code            → applied to the relevant file(s) in ~/bolt/
  4. (--pr) GitHub PRs in bolt + bolt-rest-assured after your approval

Usage:
  qa <TICKET-ID> [--env team1|team2|staging|play] [--pr] [--base main]

Environment variables required:
  ANTHROPIC_API_KEY   – Anthropic API key
  YOUTRACK_TOKEN      – YouTrack permanent token (or --yt-token)
  GITHUB_TOKEN        – GitHub personal access token (required only for --pr)
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import subprocess

import requests

# ─── Config ───────────────────────────────────────────────────────────────────

YOUTRACK_BASE      = "https://realbrokerage.youtrack.cloud/api"
GITHUB_API         = "https://api.github.com"
BOLT_REPO_PATH     = Path.home() / "bolt"
BOLT_GITHUB_REPO   = "Realtyka/bolt"
RA_REPO_PATH       = Path.home() / "bolt-rest-assured"
RA_GITHUB_REPO     = "manepranal/bolt-rest-assured"
REST_ASSURED_DIR   = RA_REPO_PATH / "src/test/java/com/real/api"
POSTMAN_DIR        = BOLT_REPO_PATH / "postman/collections"

SERVICES = [
    "arrakis", "keymaker", "yenta", "hermes", "wallet", "leo", "mufasa",
    "wanderer", "sherlock", "yada", "memento", "bff", "dropbox", "avalon",
    "mercury", "atlantis", "signature-api", "plutus", "insignia", "sirius",
    "hawkeye", "yenta-worker",
]

ENV_DOMAINS = {
    "team1":   "{service}.team1realbrokerage.com",
    "team2":   "{service}.team2realbrokerage.com",
    "team3":   "{service}.team3realbrokerage.com",
    "team4":   "{service}.team4realbrokerage.com",
    "play":    "{service}.playrealbrokerage.com",
    "staging": "{service}.stagerealbrokerage.com",
}

# ─── YouTrack helpers ─────────────────────────────────────────────────────────

def fetch_ticket(ticket_id: str, token: str) -> dict:
    fields = (
        "id,idReadable,summary,description,"
        "type(name),priority(name),state(name),"
        "tags(name),"
        "customFields(name,value(name,text,id))"
    )
    resp = requests.get(
        f"{YOUTRACK_BASE}/issues/{ticket_id}",
        params={"fields": fields},
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=15,
    )
    if resp.status_code == 404:
        sys.exit(f"Ticket '{ticket_id}' not found in YouTrack.")
    resp.raise_for_status()
    return resp.json()


def ticket_summary(ticket: dict) -> str:
    lines = [
        f"Ticket ID   : {ticket.get('idReadable', ticket.get('id'))}",
        f"Summary     : {ticket.get('summary', 'N/A')}",
        f"Type        : {_nested(ticket, 'type', 'name')}",
        f"Priority    : {_nested(ticket, 'priority', 'name')}",
        f"State       : {_nested(ticket, 'state', 'name')}",
    ]
    tags = [t["name"] for t in ticket.get("tags", [])]
    if tags:
        lines.append(f"Tags        : {', '.join(tags)}")
    desc = ticket.get("description", "").strip()
    if desc:
        lines.append(f"\nDescription:\n{desc}")
    cf_lines = []
    for cf in ticket.get("customFields", []):
        val = cf.get("value")
        if val is None:
            continue
        if isinstance(val, dict):
            val = val.get("name") or val.get("text") or str(val)
        elif isinstance(val, list):
            val = ", ".join(
                (v.get("name") or v.get("text") or str(v)) if isinstance(v, dict) else str(v)
                for v in val
            )
        cf_lines.append(f"  {cf['name']}: {val}")
    if cf_lines:
        lines.append("\nCustom Fields:\n" + "\n".join(cf_lines))
    return "\n".join(lines)


def _nested(d: dict, *keys):
    for k in keys:
        if not isinstance(d, dict):
            return "N/A"
        d = d.get(k, {})
    return d if isinstance(d, str) else "N/A"

# ─── Source file search ───────────────────────────────────────────────────────

def find_relevant_files(ticket: dict, max_files: int = 5) -> list[tuple[Path, str]]:
    """
    Search bolt/src for files relevant to the ticket.
    Returns list of (path, content) tuples.
    """
    summary = ticket.get("summary", "")
    description = ticket.get("description", "") or ""

    # Extract keywords from summary + description
    text = f"{summary} {description}".lower()
    keywords = []

    # Component-level hints
    if any(w in text for w in ["modal", "side modal", "sidebar", "drawer"]):
        keywords += ["Modal", "Sidebar", "Drawer", "SideModal"]
    if any(w in text for w in ["transaction coordinator", "tc ", "coordinator"]):
        keywords += ["TransactionCoordinator", "ManageTCSidebar", "TCRequest"]
    if any(w in text for w in ["leader", "team"]):
        keywords += ["Teams", "Leader"]
    if any(w in text for w in ["view", "button", "click"]):
        keywords += ["Button", "View"]
    if any(w in text for w in ["wallet", "payment"]):
        keywords += ["Wallet", "Payment"]
    if any(w in text for w in ["onboarding"]):
        keywords += ["Onboarding"]
    if any(w in text for w in ["checklist", "sherlock"]):
        keywords += ["Checklist", "Sherlock"]

    if not keywords:
        return []

    src_dir = BOLT_REPO_PATH / "src"
    found = []
    seen_paths = set()

    for kw in keywords:
        results = subprocess.run(
            ["grep", "-rl", kw, str(src_dir), "--include=*.tsx", "--include=*.ts",
             "--exclude-dir=openapi", "--exclude-dir=__tests__", "--exclude-dir=testUtils"],
            capture_output=True, text=True,
        )
        for line in results.stdout.strip().splitlines():
            p = Path(line)
            if p not in seen_paths and p.stat().st_size < 50_000:
                seen_paths.add(p)
                found.append(p)
            if len(found) >= max_files:
                break
        if len(found) >= max_files:
            break

    result = []
    for p in found[:max_files]:
        try:
            content = p.read_text(errors="ignore")
            result.append((p, content))
        except Exception:
            pass
    return result

# ─── Claude generation ────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a senior full-stack QA/dev engineer working on the Real Brokerage "bolt" platform.
Bolt is a React + TypeScript frontend with a Java microservices backend.

Backend services: arrakis, keymaker, yenta, hermes, wallet, leo, mufasa, wanderer,
sherlock, yada, memento, bff, dropbox, avalon, mercury, atlantis, signature-api,
plutus, insignia, sirius, hawkeye, yenta-worker.

Frontend source is at ~/bolt/src/ — components in src/components/, routes in src/routes/.

Test infrastructure (REST Assured):
- Project at ~/bolt-rest-assured/ (Maven + JUnit 5 + REST Assured 5.5.1 + Java 17)
- Base class: com.real.api.BaseTest — provides baseSpec(serviceName)
- Tests extend BaseTest, annotated with @Tag("servicename")
- Base URLs: https://{service}.{env}realbrokerage.com

Postman collection format: standard Postman Collection v2.1 JSON.

You MUST output exactly FOUR sections separated by these exact markers:

=== REST_ASSURED_TEST ===
(complete Java test class, no markdown fences)

=== POSTMAN_COLLECTION ===
(complete valid Postman Collection v2.1 JSON, no markdown fences)

=== BUG_FIX_CODE ===
For each file that needs changing, output a block in this exact format (repeat for multiple files):
FILE: src/path/to/file.tsx
<<<<<<< ORIGINAL
(the original lines to replace — copy exactly from the source provided)
=======
(the fixed replacement lines)
>>>>>>> FIXED

If this is a story/task with no bug fix needed, output: N/A

=== BUG_FIX_EXPLANATION ===
Plain-English explanation of what the bug is and what the fix does.
For stories: describe what was implemented and how to verify it.

Rules:
- For bugs: REST Assured test should reproduce the bug (FAIL before fix, PASS after).
- For stories: include happy-path + edge case tests.
- Use realistic placeholder UUIDs with TODO comments where real IDs are needed.
- Class name = ticket ID CamelCase + "Test", e.g. RV264044Test
- Postman collection name = ticket ID + short summary.
- In BUG_FIX_CODE, use the EXACT lines from the source files provided — do not paraphrase.
- Keep fixes minimal — change only what is necessary to fix the bug."""


def generate_artifacts(
    ticket_text: str,
    ticket_id: str,
    env: str,
    source_files: list[tuple[Path, str]],
) -> dict:
    source_context = ""
    if source_files:
        source_context = "\n\n--- RELEVANT SOURCE FILES ---\n"
        for path, content in source_files:
            rel = path.relative_to(BOLT_REPO_PATH)
            source_context += f"\nFILE: {rel}\n```\n{content[:6000]}\n```\n"
        source_context += "--- END SOURCE FILES ---"

    user_msg = (
        f"Generate QA artifacts for this YouTrack ticket.\n"
        f"Target environment: {env}\n\n"
        f"--- TICKET ---\n{ticket_text}\n--- END TICKET ---"
        f"{source_context}\n\n"
        f"Output exactly the four sections with the markers specified."
    )

    print(f"\nAsking Claude to generate artifacts for {ticket_id}...")
    if source_files:
        print(f"  (included {len(source_files)} relevant source file(s) for context)")

    result = subprocess.run(
        ["claude", "-p", user_msg, "--system-prompt", SYSTEM_PROMPT,
         "--model", "sonnet", "--dangerously-skip-permissions"],
        capture_output=True,
        text=True,
        timeout=600,
    )
    if result.returncode != 0:
        sys.exit(f"ERROR: claude CLI failed:\n{result.stderr.strip()}")
    return parse_sections(result.stdout, ticket_id)


def parse_sections(raw: str, ticket_id: str) -> dict:
    markers = [
        ("rest_assured",      "=== REST_ASSURED_TEST ==="),
        ("postman",           "=== POSTMAN_COLLECTION ==="),
        ("bug_fix_code",      "=== BUG_FIX_CODE ==="),
        ("bug_fix_explanation", "=== BUG_FIX_EXPLANATION ==="),
    ]
    result = {}
    for i, (key, marker) in enumerate(markers):
        next_marker = markers[i + 1][1] if i + 1 < len(markers) else None
        pattern = (
            re.escape(marker) + r"(.*?)" + re.escape(next_marker)
            if next_marker
            else re.escape(marker) + r"(.*)"
        )
        m = re.search(pattern, raw, re.DOTALL)
        if not m:
            print(f"WARNING: section '{marker}' not found in Claude response.")
        result[key] = m.group(1).strip() if m else ""
    return result

# ─── Save files ───────────────────────────────────────────────────────────────

def class_name_from_ticket(ticket_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", ticket_id) + "Test"


def save_rest_assured(java_code: str, ticket_id: str) -> Path:
    m = re.search(r"class\s+(\w+)\s+extends", java_code)
    class_name = m.group(1) if m else class_name_from_ticket(ticket_id)
    path = REST_ASSURED_DIR / f"{class_name}.java"
    path.write_text(java_code)
    return path


def save_postman(json_str: str, ticket_id: str) -> Path:
    json_str = re.sub(r"^```[a-z]*\n?", "", json_str, flags=re.MULTILINE)
    json_str = re.sub(r"```$", "", json_str, flags=re.MULTILINE).strip()
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"WARNING: Postman JSON parse error: {e}")
        data = {"raw": json_str}
    path = POSTMAN_DIR / f"{ticket_id.replace('-', '_')}.postman_collection.json"
    path.write_text(json.dumps(data, indent=2))
    return path


def apply_fix_code(fix_code: str) -> list[Path]:
    """
    Parse and apply BUG_FIX_CODE blocks to actual files in the bolt repo.
    Returns list of modified file paths.
    """
    if not fix_code or fix_code.strip().upper() == "N/A":
        return []

    # Pattern: FILE: path\n<<<<<<< ORIGINAL\n...\n=======\n...\n>>>>>>> FIXED
    block_pattern = re.compile(
        r"FILE:\s*(.+?)\n<{7} ORIGINAL\n(.*?)\n={7}\n(.*?)\n>{7} FIXED",
        re.DOTALL,
    )

    modified = []
    for match in block_pattern.finditer(fix_code):
        rel_path = match.group(1).strip()
        original = match.group(2)
        fixed = match.group(3)

        full_path = BOLT_REPO_PATH / rel_path
        if not full_path.exists():
            print(f"  WARNING: File not found for fix: {rel_path}")
            continue

        content = full_path.read_text(errors="ignore")
        if original not in content:
            print(f"  WARNING: Original code not found in {rel_path} — skipping apply.")
            print(f"  (Claude may have paraphrased — review manually)")
            continue

        full_path.write_text(content.replace(original, fixed, 1))
        modified.append(full_path)
        print(f"  Fix applied → {rel_path}")

    return modified

# ─── Git helpers ──────────────────────────────────────────────────────────────

def git(repo: Path, *args, check=True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=check,
    )


def git_has_remote(repo: Path) -> bool:
    return bool(git(repo, "remote", check=False).stdout.strip())


def git_default_branch(repo: Path) -> str:
    result = git(repo, "remote", "show", "origin", check=False)
    m = re.search(r"HEAD branch:\s+(\S+)", result.stdout)
    return m.group(1) if m else "main"


def create_branch(repo: Path, branch: str):
    existing = git(repo, "branch", "--list", branch).stdout.strip()
    if existing:
        git(repo, "checkout", branch)
        print(f"  Switched to existing branch '{branch}'")
    else:
        git(repo, "checkout", "-b", branch)
        print(f"  Created branch '{branch}'")


def stage_and_commit(repo: Path, files: list[Path], message: str) -> bool:
    for f in files:
        git(repo, "add", str(f))
    staged = git(repo, "diff", "--cached", "--name-only").stdout.strip()
    if not staged:
        print("  Nothing new to commit (files unchanged).")
        return False
    git(repo, "commit", "-m", message)
    print(f"  Committed:\n    " + "\n    ".join(staged.splitlines()))
    return True


def push_branch(repo: Path, branch: str):
    print(f"  Pushing '{branch}'...")
    git(repo, "push", "-u", "origin", branch)

# ─── GitHub API ───────────────────────────────────────────────────────────────

def github_create_pr(github_repo: str, head: str, base: str,
                     title: str, body: str, token: str) -> str:
    resp = requests.post(
        f"{GITHUB_API}/repos/{github_repo}/pulls",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"title": title, "body": body, "head": head, "base": base},
        timeout=20,
    )
    if resp.status_code == 422:
        for e in resp.json().get("errors", []):
            if "already exists" in str(e.get("message", "")):
                r2 = requests.get(
                    f"{GITHUB_API}/repos/{github_repo}/pulls",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"head": f"{github_repo.split('/')[0]}:{head}", "state": "open"},
                    timeout=15,
                )
                if r2.ok and r2.json():
                    return r2.json()[0]["html_url"] + " (already existed)"
    resp.raise_for_status()
    return resp.json()["html_url"]

# ─── PR flow ──────────────────────────────────────────────────────────────────

def pr_flow(
    ticket_id: str,
    ticket: dict,
    artifacts: dict,
    saved: dict,
    base_branch: str,
    github_token: str,
):
    branch = f"qa/{ticket_id.lower()}"
    summary = ticket.get("summary", "")
    pr_title = f"QA: {ticket_id} — {summary[:60]}{'...' if len(summary) > 60 else ''}"
    ticket_url = f"https://realbrokerage.youtrack.cloud/issue/{ticket_id}"
    env = saved.get("env", "team1")

    explanation = artifacts.get("bug_fix_explanation", "").strip()
    has_fix = bool(saved.get("fix_files"))

    # ── bolt PR body ──────────────────────────────────────────────────────────
    bolt_files = []
    if saved.get("postman"):
        bolt_files.append(saved["postman"])
    if saved.get("fix_files"):
        bolt_files.extend(saved["fix_files"])

    bolt_pr_body = (
        f"## YouTrack\n[{ticket_id}]({ticket_url}) — {summary}\n\n"
        f"## Changes\n"
        + ("- Bug fix applied to source file(s)\n" if has_fix else "")
        + "- Postman collection for manual verification\n\n"
        f"## Environment\n`{env}`\n\n"
        + (f"## What was fixed\n{explanation}\n" if explanation else "")
    )

    # ── bolt-rest-assured PR body ─────────────────────────────────────────────
    ra_files = []
    if saved.get("rest_assured"):
        ra_files.append(saved["rest_assured"])

    ra_pr_body = (
        f"## YouTrack\n[{ticket_id}]({ticket_url}) — {summary}\n\n"
        f"## Changes\n"
        f"- REST Assured test: `{saved['rest_assured'].name if saved.get('rest_assured') else ''}`\n\n"
        f"## Run\n```bash\nmvn test -P{env} "
        f"-Dtest={saved['rest_assured'].stem if saved.get('rest_assured') else ''}\n```\n"
    )

    # ── Preview ───────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("PR PREVIEW — Review before raising")
    print(f"{'='*60}")

    prs = []

    if bolt_files and git_has_remote(BOLT_REPO_PATH):
        print(f"\n[1] Realtyka/bolt")
        print(f"    Branch : {branch}  →  {base_branch}")
        print(f"    Title  : {pr_title}")
        print(f"    Files  :")
        for f in bolt_files:
            print(f"      • {Path(f).relative_to(BOLT_REPO_PATH)}")
        if explanation:
            print(f"\n    Fix summary:\n      {explanation[:300].replace(chr(10), chr(10) + '      ')}")
        prs.append({
            "label": "Realtyka/bolt",
            "repo_path": BOLT_REPO_PATH,
            "github_repo": BOLT_GITHUB_REPO,
            "files": bolt_files,
            "body": bolt_pr_body,
            "has_remote": True,
        })

    if ra_files:
        ra_has_remote = git_has_remote(RA_REPO_PATH)
        print(f"\n[2] manepranal/bolt-rest-assured")
        print(f"    Branch : {branch}  →  {base_branch}")
        print(f"    Title  : {pr_title}")
        print(f"    Files  :")
        for f in ra_files:
            print(f"      • {Path(f).name}")
        if not ra_has_remote:
            print(f"    ⚠  No remote — will commit locally only.")
        prs.append({
            "label": "manepranal/bolt-rest-assured",
            "repo_path": RA_REPO_PATH,
            "github_repo": RA_GITHUB_REPO if ra_has_remote else None,
            "files": ra_files,
            "body": ra_pr_body,
            "has_remote": ra_has_remote,
        })

    if not prs:
        print("Nothing to raise a PR for.")
        return

    print(f"\n{'='*60}")
    answer = input("Raise PR(s)? [y/N]: ").strip().lower()
    if answer != "y":
        print("PR creation cancelled.")
        return

    commit_msg = f"qa({ticket_id}): add QA artifacts and bug fix\n\nYouTrack: {ticket_url}"

    for pr in prs:
        print(f"\n── {pr['label']} ──")
        try:
            create_branch(pr["repo_path"], branch)
            committed = stage_and_commit(pr["repo_path"], pr["files"], commit_msg)
            if pr["github_repo"] and pr["has_remote"]:
                if committed:
                    push_branch(pr["repo_path"], branch)
                url = github_create_pr(
                    github_repo=pr["github_repo"],
                    head=branch,
                    base=base_branch,
                    title=pr_title,
                    body=pr["body"],
                    token=github_token,
                )
                print(f"  PR raised → {url}")
            else:
                print(f"  Committed locally on '{branch}' (no remote — set one to push).")
        except subprocess.CalledProcessError as e:
            print(f"  ERROR (git): {e.stderr.strip()}")
        except requests.HTTPError as e:
            print(f"  ERROR (GitHub API): {e.response.text}")

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="YouTrack QA Agent — ticket → tests + fix code + optional PRs"
    )
    parser.add_argument("ticket_id", help="YouTrack ticket ID, e.g. RV2-64044")
    parser.add_argument(
        "--env", default="team1",
        choices=["team1", "team2", "team3", "team4", "play", "staging"],
        help="Target environment (default: team1)",
    )
    parser.add_argument("--pr", action="store_true",
        help="Create git branches + raise GitHub PRs (requires GITHUB_TOKEN)")
    parser.add_argument("--base", default=None,
        help="Base branch for PRs (default: auto-detected)")
    parser.add_argument("--yt-token", help="YouTrack token (overrides YOUTRACK_TOKEN)")
    args = parser.parse_args()

    # ── Auth ──────────────────────────────────────────────────────────────────
    yt_token = args.yt_token or os.getenv("YOUTRACK_TOKEN")
    if not yt_token:
        sys.exit("ERROR: YOUTRACK_TOKEN not set.\nRun: export YOUTRACK_TOKEN=your_token")

    github_token = os.getenv("GITHUB_TOKEN") if args.pr else None
    if args.pr and not github_token:
        sys.exit(
            "ERROR: --pr requires GITHUB_TOKEN.\n"
            "Create one at https://github.com/settings/tokens (repo scope)\n"
            "Then: export GITHUB_TOKEN=ghp_your_token"
        )

    ticket_id = args.ticket_id.upper()

    # ── 1. Fetch ticket ───────────────────────────────────────────────────────
    print(f"Fetching {ticket_id} from YouTrack...")
    ticket = fetch_ticket(ticket_id, yt_token)
    text = ticket_summary(ticket)
    print(f"\n{'='*60}\n{text}\n{'='*60}\n")

    # ── 2. Find relevant source files ─────────────────────────────────────────
    print("Searching bolt source for relevant files...")
    source_files = find_relevant_files(ticket)
    if source_files:
        for p, _ in source_files:
            print(f"  Found: {p.relative_to(BOLT_REPO_PATH)}")
    else:
        print("  No matching source files found — Claude will infer from ticket only.")

    # ── 3. Generate artifacts ─────────────────────────────────────────────────
    artifacts = generate_artifacts(text, ticket_id, args.env, source_files)
    saved = {"env": args.env}

    # ── 4. Save REST Assured test ─────────────────────────────────────────────
    if artifacts.get("rest_assured"):
        path = save_rest_assured(artifacts["rest_assured"], ticket_id)
        saved["rest_assured"] = path
        print(f"\nREST Assured test saved  → {path}")
    else:
        print("\nWARNING: No REST Assured test generated.")

    # ── 5. Save Postman collection ────────────────────────────────────────────
    if artifacts.get("postman"):
        path = save_postman(artifacts["postman"], ticket_id)
        saved["postman"] = path
        print(f"Postman collection saved → {path}")
    else:
        print("WARNING: No Postman collection generated.")

    # ── 6. Apply bug fix code ─────────────────────────────────────────────────
    fix_code = artifacts.get("bug_fix_code", "").strip()
    explanation = artifacts.get("bug_fix_explanation", "").strip()

    if fix_code and fix_code.upper() != "N/A":
        print(f"\nApplying bug fix code...")
        modified = apply_fix_code(fix_code)
        saved["fix_files"] = modified
        if explanation:
            print(f"\n{'='*60}\nBUG FIX EXPLANATION\n{'='*60}\n{explanation}")
    else:
        saved["fix_files"] = []
        if explanation:
            print(f"\n{'='*60}\nNOTES\n{'='*60}\n{explanation}")
        else:
            print("\n(No bug fix — this appears to be a story/task.)")

    # ── 7. PR flow ────────────────────────────────────────────────────────────
    if args.pr:
        base = args.base or git_default_branch(BOLT_REPO_PATH)
        pr_flow(
            ticket_id=ticket_id,
            ticket=ticket,
            artifacts=artifacts,
            saved=saved,
            base_branch=base,
            github_token=github_token,
        )

    print(f"\nDone! Artifacts generated for {ticket_id}.")


if __name__ == "__main__":
    main()
