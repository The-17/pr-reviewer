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
            response.raise_for_status()
        else:
            logger.info(f"Successfully merged PR #{pr_number}")

class GeminiClient:
    """Handles communication with the Google Gemini API using ReAct Tool-Calling."""
    def __init__(self, api_key):
        self.api_key = api_key
        self.url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
        self.system_instruction = (
            "You are a production-grade automated code reviewer ReAct agent.\n"
            "You are equipped with tools to assist you:\n"
            "- `read_repo_file`: inspect any file in the workspace.\n"
            "- `post_line_comment`: post a review comment on a specific line of a file in the PR.\n"
            "- `submit_review`: submit the final decision (APPROVE or REJECT) and overall summary of the PR.\n\n"
            "Analyze the changes in the provided diffs. Look for security flaws, bugs, and style issues.\n"
            "If you need to inspect related files (such as config, env, or dependencies) to perform the review, use `read_repo_file`.\n"
            "You must call `post_line_comment` for any issue you find.\n"
            "Once you are done, you MUST call `submit_review` to complete the review lifecycle.\n"
            "Set the decision to 'REJECT' if any critical security issue or bug is identified."
        )

    def chat(self, messages, tools_decl):
        gemini_contents = []
        for msg in messages:
            role = msg["role"]
            if role == "user":
                gemini_contents.append({
                    "role": "user",
                    "parts": [{"text": msg["content"]}]
                })
            elif role == "assistant":
                parts = []
                if msg.get("content"):
                    parts.append({"text": msg["content"]})
                if msg.get("tool_calls"):
                    for tc in msg["tool_calls"]:
                        parts.append({
                            "functionCall": {
                                "name": tc["name"],
                                "args": tc["args"]
                            }
                        })
                gemini_contents.append({
                    "role": "model",
                    "parts": parts
                })
            elif role == "tool":
                gemini_contents.append({
                    "role": "function",
                    "parts": [{
                        "functionResponse": {
                            "name": msg["name"],
                            "response": {"content": msg["content"]}
                        }
                    }]
                })

        function_declarations = []
        for tool in tools_decl:
            fd = {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": {
                    "type": "OBJECT",
                    "properties": {},
                    "required": tool["parameters"].get("required", [])
                }
            }
            for prop_name, prop_val in tool["parameters"]["properties"].items():
                fd["parameters"]["properties"][prop_name] = {
                    "type": prop_val["type"].upper(),
                    "description": prop_val.get("description", "")
                }
                if "enum" in prop_val:
                    fd["parameters"]["properties"][prop_name]["enum"] = prop_val["enum"]
            function_declarations.append(fd)

        payload = {
            "systemInstruction": {"parts": [{"text": self.system_instruction}]},
            "contents": gemini_contents,
            "tools": [{"functionDeclarations": function_declarations}]
        }

        response = requests.post(self.url, json=payload, headers={"Content-Type": "application/json"})
        response.raise_for_status()

        resp_json = response.json()
        candidate = resp_json["candidates"][0]
        content = candidate["content"]
        parts = content.get("parts", [])

        reply_text = ""
        tool_calls = []
        for part in parts:
            if "text" in part:
                reply_text += part["text"]
            if "functionCall" in part:
                fc = part["functionCall"]
                tool_calls.append({
                    "id": None,
                    "name": fc["name"],
                    "args": fc.get("args", {})
                })

        assistant_msg = {
            "role": "assistant",
            "content": reply_text if reply_text else None
        }
        if tool_calls:
            assistant_msg["tool_calls"] = tool_calls

        class ChatResponse:
            def __init__(self, message, text, tool_calls):
                self.message = message
                self.text = text
                self.tool_calls = tool_calls

        return ChatResponse(assistant_msg, reply_text, tool_calls)

    def format_tool_response(self, tool_call_id, name, content):
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": name,
            "content": str(content)
        }

class NvidiaClient:
    """Handles communication with the NVIDIA API Catalog (OpenAI compatible) with Tool-Calling."""
    def __init__(self, api_key, model="meta/llama-3.1-70b-instruct"):
        self.api_key = api_key
        self.model = model
        self.url = "https://integrate.api.nvidia.com/v1/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        self.system_instruction = (
            "You are a production-grade automated code reviewer ReAct agent.\n"
            "You are equipped with tools to assist you:\n"
            "- `read_repo_file`: inspect any file in the workspace.\n"
            "- `post_line_comment`: post a review comment on a specific line of a file in the PR.\n"
            "- `submit_review`: submit the final decision (APPROVE or REJECT) and overall summary of the PR.\n\n"
            "Analyze the changes in the provided diffs. Look for security flaws, bugs, and style issues.\n"
            "If you need to inspect related files (such as config, env, or dependencies) to perform the review, use `read_repo_file`.\n"
            "You must call `post_line_comment` for any issue you find.\n"
            "Once you are done, you MUST call `submit_review` to complete the review lifecycle.\n"
            "Set the decision to 'REJECT' if any critical security issue or bug is identified."
        )

    def chat(self, messages, tools_decl):
        nvidia_messages = [{"role": "system", "content": self.system_instruction}]
        for msg in messages:
            role = msg["role"]
            if role == "user":
                nvidia_messages.append({
                    "role": "user",
                    "content": msg["content"]
                })
            elif role == "assistant":
                item = {
                    "role": "assistant",
                    "content": msg["content"]
                }
                if msg.get("tool_calls"):
                    item["tool_calls"] = []
                    for tc in msg["tool_calls"]:
                        item["tool_calls"].append({
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc["args"])
                            }
                        })
                nvidia_messages.append(item)
            elif role == "tool":
                nvidia_messages.append({
                    "role": "tool",
                    "tool_call_id": msg["tool_call_id"],
                    "name": msg["name"],
                    "content": msg["content"]
                })

        nvidia_tools = []
        for tool in tools_decl:
            nvidia_tools.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["parameters"]
                }
            })

        payload = {
            "model": self.model,
            "messages": nvidia_messages,
            "tools": nvidia_tools,
            "temperature": 0.2,
            "max_tokens": 2048
        }

        import time
        import random
        max_retries = 5
        backoff_factor = 2

        for attempt in range(max_retries):
            logger.info(f"Submitting chat history to NVIDIA ({self.model}) (Attempt {attempt + 1}/{max_retries})...")
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

        resp_json = response.json()
        message = resp_json["choices"][0]["message"]
        reply_text = message.get("content")

        tool_calls = []
        if "tool_calls" in message:
            for tc in message["tool_calls"]:
                tool_calls.append({
                    "id": tc["id"],
                    "name": tc["function"]["name"],
                    "args": json.loads(tc["function"]["arguments"])
                })

        assistant_msg = {
            "role": "assistant",
            "content": reply_text
        }
        if tool_calls:
            assistant_msg["tool_calls"] = tool_calls

        class ChatResponse:
            def __init__(self, message, text, tool_calls):
                self.message = message
                self.text = text
                self.tool_calls = tool_calls

        return ChatResponse(assistant_msg, reply_text, tool_calls)

    def format_tool_response(self, tool_call_id, name, content):
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": name,
            "content": str(content)
        }

class PRReviewerAgent:
    """Orchestrates the ReAct code reviewer agent loop."""
    def __init__(self, github: GithubClient, llm):
        self.github = github
        self.llm = llm
        self.skip_extensions = set((".png", ".jpg", ".jpeg", ".pdf", ".lock", ".ico", ".svg", ".zip", ".tar.gz"))
        self.valid_paths = set()

    def _should_skip(self, filename):
        ext = os.path.splitext(filename)[1].lower()
        if ext in self.skip_extensions or "lock" in filename.lower():
            return True
        return False

    def _resolve_file_path(self, llm_path, valid_paths):
        if not llm_path:
            return ""
        clean_path = llm_path.replace("\\", "/").strip("/")
        if clean_path in valid_paths:
            return clean_path
            
        parts = clean_path.split("/")
        cleaned_parts = []
        for part in parts:
            if not cleaned_parts or part != cleaned_parts[-1]:
                cleaned_parts.append(part)
        deduped_path = "/".join(cleaned_parts)
        if deduped_path in valid_paths:
            return deduped_path
            
        suffix_matches = [vp for vp in valid_paths if clean_path.endswith(vp) or vp.endswith(clean_path)]
        if len(suffix_matches) == 1:
            return suffix_matches[0]
            
        basename = os.path.basename(clean_path)
        basename_matches = [vp for vp in valid_paths if os.path.basename(vp) == basename]
        if len(basename_matches) == 1:
            return basename_matches[0]
            
        return clean_path

    def read_repo_file(self, path):
        """Reads a file from the repository, returning its content as a string."""
        if not path:
            return "Error: Path cannot be empty."
        
        # Normalize and resolve relative to BASE_DIR or workspace root
        full_path = os.path.abspath(path)
        if not os.path.exists(full_path):
            full_path = os.path.abspath(os.path.join(BASE_DIR, path))
            
        logger.info(f"Reading file: {path} (Resolved: {full_path})")
        
        if not os.path.exists(full_path):
            return f"Error: File not found at {path}"
            
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"Error reading file: {str(e)}"

    def post_line_comment(self, pr_number, commit_sha, file_path, line_number, message, suggestion=None):
        """Posts a review comment bound to a specific line in the PR diff."""
        resolved_file = self._resolve_file_path(file_path, self.valid_paths)
        body = f"**[REVIEW ISSUE]** {message}"
        if suggestion:
            body += f"\nSuggest: `{suggestion}`"
            
        try:
            self.github.post_line_comment(
                pr_number=pr_number,
                commit_sha=commit_sha,
                file_path=resolved_file,
                line_number=int(line_number),
                body=body
            )
            return f"Successfully posted line comment on {resolved_file}:{line_number}."
        except Exception as e:
            logger.warning(f"Failed to post line comment on {resolved_file}:{line_number} - {str(e)}")
            return f"Error posting line comment: {str(e)}"

    def submit_review(self, pr_number, commit_sha, decision, summary):
        """Submits the final review decision (APPROVE/REJECT) and general comment summary."""
        body = f"### Code Review Summary\n\n{summary}\n\n**Decision**: {decision}"
        try:
            self.github.post_general_comment(pr_number, body)
            if decision == "APPROVE":
                try:
                    self.github.merge_pull_request(pr_number, commit_sha)
                    return f"Successfully submitted review with decision {decision} and merged PR."
                except Exception as merge_err:
                    return f"Successfully submitted review with decision {decision}, but merge failed: {str(merge_err)}"
            else:
                return f"Successfully submitted review with decision {decision}. PR remains open."
        except Exception as e:
            return f"Error submitting review: {str(e)}"

    def run(self):
        try:
            pr = self.github.fetch_oldest_open_pr()
            if not pr:
                logger.info("No open PRs found. Exiting.")
                return

            pr_num = pr["number"]
            commit_sha = pr["head"]["sha"]
            logger.info(f"Processing PR #{pr_num} (Commit: {commit_sha[:7]})...")

            files = self.github.fetch_pr_files(pr_num)
            diffs_to_review = []
            self.valid_paths = {f["filename"] for f in files}

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

            tools_declaration = [
                {
                    "name": "read_repo_file",
                    "description": "Reads the content of a file inside the repository path.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "path": {"type": "STRING", "description": "The relative path of the file to read."}
                        },
                        "required": ["path"]
                    }
                },
                {
                    "name": "post_line_comment",
                    "description": "Posts a review comment bound to a specific line in a PR file.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "file": {"type": "STRING", "description": "The relative path of the file."},
                            "line": {"type": "INTEGER", "description": "The line number in the file."},
                            "message": {"type": "STRING", "description": "Review comment message detailing the issue."},
                            "suggestion": {"type": "STRING", "description": "Optional code suggestion for the fix."}
                        },
                        "required": ["file", "line", "message"]
                    }
                },
                {
                    "name": "submit_review",
                    "description": "Submits the overall review decision for the pull request.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "decision": {"type": "STRING", "enum": ["APPROVE", "REJECT"], "description": "The overall PR review decision."},
                            "summary": {"type": "STRING", "description": "A summary of the review findings."}
                        },
                        "required": ["decision", "summary"]
                    }
                }
            ]

            initial_prompt = f"Review these diffs:\n" + "\n\n".join(diffs_to_review)
            messages = [{"role": "user", "content": initial_prompt}]

            max_turns = 10
            turn = 0
            submitted = False

            while turn < max_turns and not submitted:
                logger.info(f"ReAct Loop Turn {turn + 1}/{max_turns}...")
                try:
                    response = self.llm.chat(messages, tools_declaration)
                except Exception as e:
                    logger.error(f"Failed to fetch response from LLM: {str(e)}")
                    self.github.post_general_comment(pr_num, f"### Code Review Error\n\nFailed to fetch review from LLM: {str(e)}")
                    return

                if response.tool_calls:
                    messages.append(response.message)
                    for tc in response.tool_calls:
                        tool_name = tc["name"]
                        tool_args = tc["args"]
                        tool_call_id = tc.get("id")

                        logger.info(f"Agent executing tool call: {tool_name} with args: {tool_args}")

                        if tool_name == "read_repo_file":
                            result = self.read_repo_file(tool_args.get("path", ""))
                        elif tool_name == "post_line_comment":
                            result = self.post_line_comment(
                                pr_num, commit_sha,
                                tool_args.get("file", ""),
                                tool_args.get("line", 0),
                                tool_args.get("message", ""),
                                tool_args.get("suggestion")
                            )
                        elif tool_name == "submit_review":
                            result = self.submit_review(
                                pr_num, commit_sha,
                                tool_args.get("decision", "REJECT"),
                                tool_args.get("summary", "")
                            )
                            submitted = True
                        else:
                            result = f"Error: Tool {tool_name} not found."

                        tool_msg = self.llm.format_tool_response(tool_call_id, tool_name, result)
                        messages.append(tool_msg)
                else:
                    logger.info(f"Agent finished turn with text reply: {response.text}")
                    messages.append(response.message)
                    # If it did not call submit_review, force complete to avoid infinite loop
                    self.submit_review(pr_num, commit_sha, "REJECT", "Agent failed to submit a structured review tool call.")
                    break

                turn += 1

        except Exception as e:
            logger.error(f"Unexpected error in agent loop: {str(e)}")

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
