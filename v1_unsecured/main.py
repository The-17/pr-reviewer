import os
import sys
import json
import logging
import requests
from decouple import config

logging.basicConfig(
    level=logging.INFO, 
    format='{"time":"%(asctime)s", "level":"%(levelname)s", "msg":"%(message)s"}'
)

logger = logging.getLogger("pre_reviewer_v1")

GITHUB_TOKEN = config("GITHUB_TOKEN", default=None)
LLM_API_KEY = config("LLM_API_KEY", default=None)
REPO_OWNER = config("REPO_OWNER", default=None)
REPO_NAME = config("REPO_NAME", default=None)

if not all([GITHUB_TOKEN, LLM_API_KEY, REPO_OWNER, REPO_NAME]):
    logger.error("Missing required environment variables in .env (GITHUB_TOKEN, LLM_API_KEY, REPO_OWNER, REPO_NAME)")

class GithubClient:
    """Handles communication with the GitHub REST API v3."""
    def __init__(self, token, owner, repo):
        self.token = token
        self.owner = owner
        self.repo = repo
        # Target repository API base URL.
        # Set to organization target: https://api.github.com/repos/the-17/pr-reviewer
        # To use a personal account, change owner to your username (e.g. https://api.github.com/repos/username/pr-reviewer)
        self.base_url = f"https://api.github.com/repos/{owner}/{repo}"
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "pre-reviewer-v1"
        }

    def fetch_oldest_open_pr(self):
        """Retrieves the oldest open pull request from the target repository."""
        url = f"{self.base_url}/pulls"
        params = {"state": "open", "sort": "created", "direction": "asc", "per_page": 1}
        response = requests.get(url, headers=self.headers, params=params)
        response.raise_for_status()
        prs = response.json()
        return prs[0] if prs else None

    def fetch_pr_files(self, pr_number):
        """Retrieves files modified in the pull request including their patches."""
        url = f"{self.base_url}/pulls/{pr_number}/files"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def post_line_comment(self, pr_number, commit_sha, file_path, line_number, body):
        """Posts a review comment bound to a specific line in the PR diff."""
        url = f"{self.base_url}/pulls/{pr_number}/comments"
        payload = {
            "body": body,
            "commit_id": commit_sha,
            "path": file_path,
            "line": line_number,
            "side": "RIGHT"
        }

        response = requests.post(url, headers=self.headers, json=payload)
        if response.status_code != 201:
            logger.warning(f"Failed to post line comment on {file_path}:{line_number} - {response.text}")
        else:
            logger.info(f"Successfully posted line comment on {file_path}:{line_number}")

    def post_general_comment(self, pr_number, body):
        """Posts a general thread comment to the pull request."""
        url = f"{self.base_url}/issues/{pr_number}/comments"
        response = requests.post(url, headers=self.headers, json={"body": body})
        response.raise_for_status()

    def merge_pull_request(self, pr_number, commit_sha):
        """Triggers the merge operation for the pull request."""
        url = f"{self.base_url}/pulls/{pr_number}/merge"  
        payload = {
            "commit_title": "Auto-merge by PR Reviewer Agent",
            "sha": commit_sha
        }

        response = requests.put(url, headers=self.headers, json=payload)
        if response.status_code != 200:
            logger.warning(f"Failed to merge PR #{pr_number} - {response.text}")
        else:
            logger.info(f"Successfully merged PR #{pr_number}")


class GeminiClient:
    """Handles communication with the Google Gemini API using Structured Outputs."""
    def __init__(self, api_key):
        self.api_key = api_key
        self.url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"

    def review_diffs(self, file_diffs_text):
        """Submits PR diffs to the LLM and requests a structured JSON review response."""
        system_instruction = (
            "You are a production-grade automated code reviewer.\n"
            "Analyze the changes in the provided diffs. Look for security flaws, bugs, and style issues.\n"
            "You must output a structured JSON review adhering to the specified schema.\n"
            "Set decision to 'REJECT' if any critical security issue or bug is identified."
        )

        schema = {
            "type": "OBJECT",
            "properties": {
                "summary": {"type": "STRING"},
                "decision": {"type": "STRING", "enum": ["APPROVE", "REJECT"]},
                "comments": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "file": {"type": "STRING"},
                            "line": {"type": "INTEGER"},
                            "category": {"type": "STRING", "enum": ["security", "performance", "style", "bug"]},
                            "severity": {"type": "STRING", "enum": ["high", "medium", "low"]},
                            "message": {"type": "STRING"},
                            "suggestion": {"type": "STRING"}
                        },
                        "required": ["file", "line", "category", "severity", "message"]
                    }
                }
            },
            "required": ["summary", "decision", "comments"]
        }

        payload = {
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "contents": [{"parts": [{"text": f"Review these diffs:\n{file_diffs_text}"}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": schema
            }
        }

        logger.info("Submitting diffs to Gemini for review...")
        response = requests.post(self.url, json=payload, headers={"Content-Type": "application/json"})
        response.raise_for_status()

        text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)


class PRReviewerAgent:
    """Orchestrates the PR retrieval, filtering, analysis, commenting, and merging lifecycle."""
    def __init__(self, github: GithubClient, gemini: GeminiClient):
        self.github = github
        self.gemini = gemini
        self.skip_extensions = set((".png", ".jpg", ".jpeg", ".pdf", ".lock", ".ico", ".svg", ".zip", ".tar.gz"))

    def _should_skip(self, filename):
        """Returns True if the file type or name should not be sent to the LLM (noise filtering)."""
        ext = os.path.splitext(filename)[1].lower()
        if ext in self.skip_extensions or "lock" in filename.lower():
            return True
        return False

    def run(self):
        pr = self.github.fetch_oldest_open_pr()
        if not pr:
            logger.info("No open PRs found. Exiting.")
            return

        pr_num = pr["number"]
        commit_sha = pr["head"]["sha"]
        logger.info(f"Processing PR #{pr_num} (Commit: {commit_sha[:7]})...")

        files = self.github.fetch_pr_files(pr_num)
        diffs_to_review = []

        for f in files:
            filename = f["filename"]
            patch = f.get("patch")
            if not patch or self._should_skip(filename):
                logger.info(f"Skipping file {filename} (binary or noise).")
                continue

            diffs_to_review.append(f"--- File: {filename}\n{patch}")

        if not diffs_to_review:
            logger.info("No valid diffs to review after filtering. Exiting.")
            return

        review_data = self.gemini.review_diffs("\n\n".join(diffs_to_review))

        # Post line comments for each issue found
        for comment in review_data.get("comments", []):
            body = (
                f"**[{comment['category'].upper()} - {comment['severity'].upper()}]** {comment['message']}\n"
                f"Suggest: `{comment.get('suggestion', '')}`"
            )

            self.github.post_line_comment(
                pr_number=pr_num,
                commit_sha=commit_sha,
                file_path=comment["file"],
                line_number=comment["line"],
                body=body
            )

        # Post overall summary and execute decision
        decision = review_data.get("decision", "REJECT")
        summary_body = f"### Code Review Summary\n\n{review_data.get('summary', '')}\n\n**Decision**: {decision}"
        self.github.post_general_comment(pr_num, summary_body)

        if decision == "REJECT":
            logger.info(f"PR #{pr_num} rejected or requires manual intervention.")
            return
        
        self.github.merge_pull_request(pr_num, commit_sha)
        logger.info(f"PR #{pr_num} approved and auto-merged successfully.")


if __name__ == "__main__":
    if not all([GITHUB_TOKEN, LLM_API_KEY, REPO_OWNER, REPO_NAME]):
        logger.error("Required env variables are not fully configured. Exiting.")
        sys.exit(1)
    gh_client = GithubClient(GITHUB_TOKEN, REPO_OWNER, REPO_NAME)
    gemini_client = GeminiClient(LLM_API_KEY)
    engine = PRReviewerAgent(gh_client, gemini_client)
    engine.run()
