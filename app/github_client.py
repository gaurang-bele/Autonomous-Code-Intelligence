import re
from urllib.parse import urlparse
import httpx

class GitHubAPIError(RuntimeError):
    pass

class GitHubClient:
    def __init__(self, token="", api_url="https://api.github.com"):
        self.api_url = api_url.rstrip("/")
        self.headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if token:
            self.headers["Authorization"] = f"Bearer {token}"

    @staticmethod
    def parse_pr_url(url):
        parsed = urlparse(url)
        match = re.fullmatch(r"/([^/]+)/([^/]+)/pull/(\d+)/?", parsed.path)
        if parsed.hostname not in ("github.com", "www.github.com") or not match:
            raise ValueError("Expected https://github.com/owner/repo/pull/123")
        return f"{match.group(1)}/{match.group(2)}", int(match.group(3))

    async def request(self, method, path, **kwargs):
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.request(method, self.api_url + path, headers=self.headers, **kwargs)
        if r.status_code >= 400:
            raise GitHubAPIError(f"GitHub API error {r.status_code}: {r.text[:500]}")
        return {} if r.status_code == 204 else r.json()

    async def fetch_pull_request(self, pr_url):
        repo, number = self.parse_pr_url(pr_url)
        pr = await self.request("GET", f"/repos/{repo}/pulls/{number}")
        files = await self.request("GET", f"/repos/{repo}/pulls/{number}/files", params={"per_page": 100})
        contents, metadata = {}, {}
        for item in files:
            name = item["filename"]
            if item.get("status") == "removed" or not item.get("raw_url"):
                continue
            if item.get("additions", 0) + item.get("deletions", 0) > 20000:
                continue
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                response = await client.get(item["raw_url"], headers=self.headers)
            response.raise_for_status()
            contents[name] = response.text
            metadata[name] = {"sha": item.get("sha"), "status": item.get("status")}
        return {"pr_url": pr_url, "repository": repo, "pr_number": number,
                "branch_name": pr["head"]["ref"], "code_contents": contents,
                "file_metadata": metadata}

    async def commit_files(self, repository, branch, files, metadata, message):
        if not self.headers.get("Authorization"):
            raise GitHubAPIError("GITHUB_TOKEN is required for approved writes")
        ref = await self.request("GET", f"/repos/{repository}/git/ref/heads/{branch}")
        parent = ref["object"]["sha"]
        commit = await self.request("GET", f"/repos/{repository}/git/commits/{parent}")
        tree_items = []
        for name, content in files.items():
            if name not in metadata:
                raise GitHubAPIError(f"Refusing to write unfetched file: {name}")
            blob = await self.request("POST", f"/repos/{repository}/git/blobs",
                                      json={"content": content, "encoding": "utf-8"})
            tree_items.append({"path": name, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        tree = await self.request("POST", f"/repos/{repository}/git/trees",
                                  json={"base_tree": commit["tree"]["sha"], "tree": tree_items})
        new_commit = await self.request("POST", f"/repos/{repository}/git/commits",
            json={"message": message, "tree": tree["sha"], "parents": [parent]})
        await self.request("PATCH", f"/repos/{repository}/git/refs/heads/{branch}",
                           json={"sha": new_commit["sha"], "force": False})
        return f"https://github.com/{repository}/commit/{new_commit['sha']}"
