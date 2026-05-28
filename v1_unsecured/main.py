import os
import sys
import json
import logging
import requests
from decouple import Config, RepositoryEnv

logging.basicConfig(
    level=logging.INFO, 
    format='{"time":"%(asctime)s", "level":"%(levelname)s", "msg":"%(message)s"}'
)

logger = logging.getLogger("pre_reviewer_v1")

# Robustly find .env in the script's directory or its parent
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(BASE_DIR, '.env')
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(BASE_DIR), '.env')

if os.path.exists(env_path):
    config = Config(RepositoryEnv(env_path))
else:
    from decouple import config

GITHUB_TOKEN = config("GITHUB_TOKEN", default=None)
LLM_API_KEY = config("LLM_API_KEY", default=None)
NVIDIA_API_KEY = config("NVIDIA_API_KEY", default=None)
NVIDIA_MODEL = config("NVIDIA_MODEL", default="meta/llama-3.1-70b-instruct")
REPO_OWNER = config("REPO_OWNER", default=None)
REPO_NAME = config("REPO_NAME", default=None)

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
            "Set decision to 'REJECT' if any critical security issue or bug is identified.\n"
            "CRITICAL: The 'file' field in each comment MUST match exactly the filename provided in the diff header (e.g. '--- File: <filename>'). Do not prepend, alter, or double the directory name of the filename."
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


class NvidiaClient:
    """Handles communication with the NVIDIA API Catalog (OpenAI compatible)."""
    def __init__(self, api_key, model="meta/llama-3.1-70b-instruct"):
        self.api_key = api_key
        self.model = model
        self.url = "https://integrate.api.nvidia.com/v1/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    def review_diffs(self, file_diffs_text):
        """Submits PR diffs to the NVIDIA API and requests a JSON review response."""
        system_instruction = (
            "You are a production-grade automated code reviewer.\n"
            "Analyze the changes in the provided diffs. Look for security flaws, bugs, and style issues.\n"
            "You must output a structured JSON review adhering to this exact schema:\n"
            "{\n"
            "  \"summary\": \"Overall summary of the review\",\n"
            "  \"decision\": \"APPROVE\" or \"REJECT\",\n"
            "  \"comments\": [\n"
            "    {\n"
            "      \"file\": \"filename\",\n"
            "      \"line\": 12,\n"
            "      \"category\": \"security\" | \"performance\" | \"style\" | \"bug\",\n"
            "      \"severity\": \"high\" | \"medium\" | \"low\",\n"
            "      \"message\": \"description of the issue\",\n"
            "      \"suggestion\": \"code replacement or fix recommendation\"\n"
            "    }\n"
            "  ]\n"
            "}\n"
            "Set decision to 'REJECT' if any critical security issue or bug is identified.\n"
            "CRITICAL: The 'file' field in each comment MUST match exactly the filename provided in the diff header (e.g. '--- File: <filename>'). Do not prepend, alter, or double the directory name of the filename."
        )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": f"Review these diffs:\n{file_diffs_text}"}
            ],
            "temperature": 0.2,
            "max_tokens": 2048,
            "response_format": {"type": "json_object"}
        }

        import time
        import random
        max_retries = 5
        backoff_factor = 2

        for attempt in range(max_retries):
            logger.info(f"Submitting diffs to NVIDIA ({self.model}) (Attempt {attempt + 1}/{max_retries})...")
            response = requests.post(self.url, json=payload, headers=self.headers)
            
            if response.status_code == 429:
                if attempt == max_retries - 1:
                    response.raise_for_status()
                sleep_time = (backoff_factor ** attempt) + random.uniform(0, 1)
                logger.warning(f"NVIDIA API rate limited (429). Retrying in {sleep_time:.2f} seconds...")
                time.sleep(sleep_time)
                continue
                
            response.raise_for_status()
            break

        response_json = response.json()
        text = response_json["choices"][0]["message"]["content"]
        
        # Clean any potential markdown code blocks (e.g. ```json ... ```)
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        
        return json.loads(text)


class PRReviewerAgent:
    """Orchestrates the PR retrieval, filtering, analysis, commenting, and merging lifecycle."""
    def __init__(self, github: GithubClient, llm):
        self.github = github
        self.llm = llm
        self.skip_extensions = set((".png", ".jpg", ".jpeg", ".pdf", ".lock", ".ico", ".svg", ".zip", ".tar.gz"))

    def _should_skip(self, filename):
        """Returns True if the file type or name should not be sent to the LLM (noise filtering)."""
        ext = os.path.splitext(filename)[1].lower()
        if ext in self.skip_extensions or "lock" in filename.lower():
            return True
        return False

    def _resolve_file_path(self, llm_path, valid_paths):
        """Normalizes and resolves the path returned by the LLM against actual PR files."""
        if not llm_path:
            return ""
        # Normalize separators
        clean_path = llm_path.replace("\\", "/").strip("/")
        
        # Exact match
        if clean_path in valid_paths:
            return clean_path
            
        # Try matching ignoring any duplicate directory prefixes (e.g. v1_unsecured/v1_unsecured/main.py)
        parts = clean_path.split("/")
        cleaned_parts = []
        for part in parts:
            if not cleaned_parts or part != cleaned_parts[-1]:
                cleaned_parts.append(part)
        deduped_path = "/".join(cleaned_parts)
        if deduped_path in valid_paths:
            return deduped_path
            
        # Suffix matching (e.g., if LLM returned 'v1_unsecured/v1_unsecured/.env.example' or 'v1_unsecured/.gitignore')
        suffix_matches = [vp for vp in valid_paths if clean_path.endswith(vp) or vp.endswith(clean_path)]
        if len(suffix_matches) == 1:
            return suffix_matches[0]
            
        # Basename matching as final fallback
        basename = os.path.basename(clean_path)
        basename_matches = [vp for vp in valid_paths if os.path.basename(vp) == basename]
        if len(basename_matches) == 1:
            return basename_matches[0]
            
        return clean_path

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

        review_data = self.llm.review_diffs("\n\n".join(diffs_to_review))

        # Post line comments for each issue found
        valid_paths = {f["filename"] for f in files}
        for comment in review_data.get("comments", []):
            llm_file = comment.get("file", "")
            resolved_file = self._resolve_file_path(llm_file, valid_paths)
            
            body = (
                f"**[{comment['category'].upper()} - {comment['severity'].upper()}]** {comment['message']}\n"
                f"Suggest: `{comment.get('suggestion', '')}`"
            )

            self.github.post_line_comment(
                pr_number=pr_num,
                commit_sha=commit_sha,
                file_path=resolved_file,
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
    if not GITHUB_TOKEN or not REPO_OWNER or not REPO_NAME:
        logger.error("Missing required GitHub environment variables (GITHUB_TOKEN, REPO_OWNER, REPO_NAME) in .env")
        sys.exit(1)

    if not LLM_API_KEY and not NVIDIA_API_KEY:
        logger.error("Missing LLM credentials. Set either LLM_API_KEY (for Gemini) or NVIDIA_API_KEY (for NVIDIA) in .env")
        sys.exit(1)

    gh_client = GithubClient(GITHUB_TOKEN, REPO_OWNER, REPO_NAME)

    if NVIDIA_API_KEY:
        logger.info("Initializing NVIDIA NIM Client...")
        llm_client = NvidiaClient(NVIDIA_API_KEY, NVIDIA_MODEL)
    else:
        logger.info("Initializing Google Gemini Client...")
        llm_client = GeminiClient(LLM_API_KEY)

    engine = PRReviewerAgent(gh_client, llm_client)
    engine.run()
