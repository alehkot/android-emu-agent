"""Publish one commit comment per Woodpecker pipeline/workflow (stdlib only)."""

import hashlib
import json
import os
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def api(method, path, body=None):
    request = Request(
        "https://api.github.com" + path,
        data=None if body is None else json.dumps(body).encode(),
        headers={
            "Authorization": "Bearer " + os.environ["GH_TOKEN"],
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "woodpecker-commit-report",
        },
        method=method,
    )
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def failure_excerpt(path):
    if not path.is_file():
        return "No build log was produced; inspect the Woodpecker pipeline."
    with path.open("rb") as stream:
        stream.seek(max(0, path.stat().st_size - 128_000))
        text = stream.read().decode("utf-8", errors="replace")
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    for key, value in os.environ.items():
        if re.search(r"TOKEN|SECRET|PASSWORD|API_KEY", key) and len(value) >= 8:
            text = text.replace(value, "[REDACTED]")
    text = re.sub(r"(?:github_pat_|gh[pousr]_|sk-)[A-Za-z0-9_-]{12,}", "[REDACTED]", text)
    lines = text.splitlines()
    selected = set()
    for index, line in enumerate(lines):
        if re.search(r"error|fail(?:ed|ure)?|traceback|assert|exception", line, re.I):
            selected.update(range(max(0, index - 1), min(len(lines), index + 3)))
    excerpt = "\n".join(lines[index] for index in sorted(selected)) if selected else text
    return excerpt[-12_000:]


def make_report():
    repo = os.environ["CI_REPO"]
    sha = os.environ["CI_COMMIT_SHA"]
    number = os.environ["CI_PIPELINE_NUMBER"]
    status = os.environ["CI_PIPELINE_STATUS"]
    workflow = os.environ["CI_WORKFLOW_NAME"]
    url = os.environ["CI_PIPELINE_URL"]
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+", repo) or repo.split("/")[
        -1
    ] in {".", ".."}:
        raise ValueError("Invalid repository name")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", sha) or not number.isdecimal():
        raise ValueError("Invalid commit SHA or pipeline number")
    if status not in {"success", "failure"}:
        raise ValueError("Report requires a completed build-step status")
    if urlsplit(url).scheme not in {"http", "https"} or not urlsplit(url).netloc:
        raise ValueError("Invalid pipeline URL")
    digest = hashlib.sha256(workflow.encode()).hexdigest()[:16]
    marker = f"<!-- woodpecker-report:{number}:{digest} -->"
    title = "PASS" if status == "success" else "FAIL"
    body = (
        f"{marker}\n### Woodpecker {title}\n\n"
        f"Commit: `{sha}`\n\nPipeline #{number} — {workflow}\n\n"
        f"[Full build logs](<{url}>)\n"
    )
    if status == "failure":
        excerpt = failure_excerpt(Path(".ci-output/build.log"))
        fence = "`" * max(3, 1 + max((len(m) for m in re.findall(r"`+", excerpt)), default=0))
        body += (
            f"\nFailure excerpt (bounded; consult full logs):\n\n{fence}text\n{excerpt}\n{fence}\n"
        )
    return repo, sha, marker, body


def main():
    if not os.environ.get("GH_TOKEN"):
        raise ValueError("Set the Woodpecker secret github_comment_token")
    repo, sha, marker, body = make_report()
    author = api("GET", "/user")["id"]
    page = 1
    while True:
        comments = api("GET", f"/repos/{repo}/commits/{sha}/comments?per_page=100&page={page}")
        for comment in comments:
            if comment["user"]["id"] == author and comment.get("body", "").startswith(marker):
                api(
                    "PATCH",
                    f"/repos/{repo}/comments/{int(comment['id'])}",
                    {"body": body},
                )
                print("Updated GitHub commit report.")
                return
        if len(comments) < 100:
            break
        page += 1
    api("POST", f"/repos/{repo}/commits/{sha}/comments", {"body": body})
    print("Created GitHub commit report.")


if __name__ == "__main__":
    try:
        main()
    except HTTPError as error:
        sys.exit(f"GitHub commit report failed: HTTP {error.code}")
    except (KeyError, ValueError, OSError, URLError) as error:
        sys.exit(f"GitHub commit report failed: {error}")
