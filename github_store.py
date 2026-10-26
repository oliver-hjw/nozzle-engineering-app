from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests


class GitHubStoreError(RuntimeError):
    pass


class ConflictError(GitHubStoreError):
    pass


@dataclass
class ProjectRef:
    name: str
    path: str
    sha: str | None = None


class GitHubProjectStore:
    """Small-team JSON project store using the GitHub Contents API.

    For Streamlit Community Cloud, point this at a *separate* private data repo so
    project saves don't look like source-code commits to the deployed app repo.
    """

    def __init__(self, token: str, repo: str, branch: str = "main", root: str = "projects"):
        if "/" not in repo:
            raise ValueError("repo must be 'owner/repository'")
        self.token = token.strip()
        self.repo = repo.strip().strip("/")
        self.branch = branch.strip() or "main"
        self.root = root.strip("/") or "projects"
        self.base = f"https://api.github.com/repos/{self.repo}/contents"
        self.headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _url(self, path: str) -> str:
        path = path.strip("/")
        return f"{self.base}/{quote(path, safe='/')}"

    def _raise(self, r: requests.Response, context: str) -> None:
        if r.status_code == 409:
            raise ConflictError(f"{context}: GitHub conflict (409)")
        detail = ""
        try:
            detail = r.json().get("message", "")
        except Exception:
            detail = r.text[:300]
        raise GitHubStoreError(f"{context}: HTTP {r.status_code} {detail}".strip())

    def health(self) -> dict[str, Any]:
        r = requests.get(
            f"https://api.github.com/repos/{self.repo}",
            headers=self.headers,
            timeout=20,
        )
        if not r.ok:
            self._raise(r, "Repository connection failed")
        data = r.json()
        return {
            "repo": data.get("full_name", self.repo),
            "private": bool(data.get("private")),
            "default_branch": data.get("default_branch"),
        }

    def list_projects(self) -> list[ProjectRef]:
        r = requests.get(
            self._url(self.root),
            headers=self.headers,
            params={"ref": self.branch},
            timeout=20,
        )
        if r.status_code == 404:
            return []
        if not r.ok:
            self._raise(r, "Could not list projects")
        rows = []
        for item in r.json():
            if item.get("type") == "file" and item.get("name", "").lower().endswith(".json"):
                rows.append(ProjectRef(item["name"], item["path"], item.get("sha")))
        rows.sort(key=lambda x: x.name.lower())
        return rows

    def read_project(self, filename: str) -> tuple[dict[str, Any], str]:
        path = f"{self.root}/{filename}"
        r = requests.get(
            self._url(path),
            headers=self.headers,
            params={"ref": self.branch},
            timeout=20,
        )
        if not r.ok:
            self._raise(r, f"Could not read {filename}")
        data = r.json()
        raw = base64.b64decode(data["content"]).decode("utf-8")
        return json.loads(raw), data["sha"]

    def get_sha(self, filename: str) -> str | None:
        path = f"{self.root}/{filename}"
        r = requests.get(
            self._url(path),
            headers=self.headers,
            params={"ref": self.branch},
            timeout=20,
        )
        if r.status_code == 404:
            return None
        if not r.ok:
            self._raise(r, f"Could not read SHA for {filename}")
        return r.json().get("sha")

    def save_project(
        self,
        filename: str,
        project: dict[str, Any],
        expected_sha: str | None,
        actor: str,
        message: str,
    ) -> str:
        path = f"{self.root}/{filename}"
        current_sha = self.get_sha(filename)

        # Optimistic concurrency: a loaded project may only overwrite the exact
        # GitHub blob it was loaded from.
        if expected_sha is not None and current_sha != expected_sha:
            raise ConflictError(
                "This project changed on GitHub after you loaded it. Reload the latest version before saving."
            )
        if expected_sha is None and current_sha is not None:
            raise ConflictError(
                "A project with this file name already exists. Reload it instead of creating over it."
            )

        content = json.dumps(project, ensure_ascii=False, indent=2).encode("utf-8")
        payload: dict[str, Any] = {
            "message": message,
            "content": base64.b64encode(content).decode("ascii"),
            "branch": self.branch,
        }
        if current_sha:
            payload["sha"] = current_sha

        r = requests.put(
            self._url(path), headers=self.headers, json=payload, timeout=30
        )
        if not r.ok:
            self._raise(r, f"Could not save {filename}")
        result = r.json()
        return result.get("content", {}).get("sha") or self.get_sha(filename) or ""

    def delete_project(self, filename: str, expected_sha: str, actor: str) -> None:
        current_sha = self.get_sha(filename)
        if not current_sha:
            raise GitHubStoreError("Project no longer exists on GitHub.")
        if current_sha != expected_sha:
            raise ConflictError(
                "This project changed after you loaded it. Reload before deleting."
            )
        path = f"{self.root}/{filename}"
        payload = {
            "message": f"Delete project {filename} by {actor}",
            "sha": current_sha,
            "branch": self.branch,
        }
        r = requests.delete(
            self._url(path), headers=self.headers, json=payload, timeout=30
        )
        if not r.ok:
            self._raise(r, f"Could not delete {filename}")


class LocalProjectStore:
    """Local-only fallback for testing. Not persistent on Community Cloud."""

    def __init__(self, root: str | Path = "projects"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def health(self) -> dict[str, Any]:
        return {"repo": "LOCAL DEMO", "private": True, "default_branch": "local"}

    def list_projects(self) -> list[ProjectRef]:
        return [ProjectRef(p.name, str(p), str(p.stat().st_mtime_ns)) for p in sorted(self.root.glob("*.json"))]

    def read_project(self, filename: str) -> tuple[dict[str, Any], str]:
        p = self.root / filename
        return json.loads(p.read_text(encoding="utf-8")), str(p.stat().st_mtime_ns)

    def get_sha(self, filename: str) -> str | None:
        p = self.root / filename
        return str(p.stat().st_mtime_ns) if p.exists() else None

    def save_project(self, filename: str, project: dict[str, Any], expected_sha: str | None, actor: str, message: str) -> str:
        p = self.root / filename
        current = self.get_sha(filename)
        if expected_sha is not None and current != expected_sha:
            raise ConflictError("Local project changed after you loaded it.")
        if expected_sha is None and current is not None:
            raise ConflictError("Local project already exists.")
        p.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(p.stat().st_mtime_ns)

    def delete_project(self, filename: str, expected_sha: str, actor: str) -> None:
        p = self.root / filename
        if self.get_sha(filename) != expected_sha:
            raise ConflictError("Local project changed after you loaded it.")
        p.unlink(missing_ok=True)
