"""Notion API client + a JSON demo store with the same interface.

Notion database properties expected (names are configurable in PROPS):
  Name (title), Platform (select), Pillar (select), Status (status or select), Publish Date (date),
  Impressions, Likes, Comments, Shares (number), Caption (rich text)
"""
from __future__ import annotations

import json
import os
import shutil
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
PROPS = {"title": "Name", "platform": "Platform", "pillar": "Pillar", "status": "Status",
         "publish_at": "Publish Date", "impressions": "Impressions", "likes": "Likes",
         "comments": "Comments", "shares": "Shares", "caption": "Caption"}


class NotionStore:
    def __init__(self, token: str, database_id: str):
        self.token, self.database_id = token, database_id

    def _request(self, method: str, path: str, body: Optional[dict] = None) -> dict:
        req = urllib.request.Request(
            f"{NOTION_API}{path}", method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": f"Bearer {self.token}", "Notion-Version": NOTION_VERSION,
                     "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read())

    def list_posts(self) -> List[dict]:
        posts, cursor = [], None
        while True:  # follow Notion's cursor-based pagination
            body = {"page_size": 100, **({"start_cursor": cursor} if cursor else {})}
            data = self._request("POST", f"/databases/{self.database_id}/query", body)
            posts += [page_to_post(p) for p in data["results"]]
            if not data.get("has_more"):
                return posts
            cursor = data["next_cursor"]

    def update_post(self, post_id: str, fields: Dict) -> None:
        self._request("PATCH", f"/pages/{post_id}", {"properties": post_to_properties(fields)})


def page_to_post(page: dict) -> dict:
    p = page["properties"]

    def text(prop):
        v = p.get(prop, {})
        items = v.get("title") or v.get("rich_text") or []
        return "".join(i.get("plain_text", "") for i in items)

    def select(prop):
        v = p.get(prop, {})
        return ((v.get("select") or v.get("status")) or {}).get("name", "")

    def number(prop):
        return p.get(prop, {}).get("number") or 0

    date = (p.get(PROPS["publish_at"], {}).get("date") or {}).get("start")
    return {"id": page["id"], "title": text(PROPS["title"]), "platform": select(PROPS["platform"]),
            "pillar": select(PROPS["pillar"]), "status": select(PROPS["status"]), "publish_at": date,
            "impressions": number(PROPS["impressions"]), "likes": number(PROPS["likes"]),
            "comments": number(PROPS["comments"]), "shares": number(PROPS["shares"]),
            "caption": text(PROPS["caption"])}


def post_to_properties(fields: Dict) -> dict:
    props = {}
    if "status" in fields:
        props[PROPS["status"]] = {"status": {"name": fields["status"]}}
    if "publish_at" in fields:
        props[PROPS["publish_at"]] = {"date": {"start": fields["publish_at"]} if fields["publish_at"] else None}
    if "caption" in fields:
        props[PROPS["caption"]] = {"rich_text": [{"text": {"content": fields["caption"][:2000]}}]}
    return props


class DemoStore:
    """Local JSON store so the app runs without a Notion workspace."""

    def __init__(self, seed: Path, state: Path):
        self.state = state
        if not state.exists():
            shutil.copy(seed, state)

    def list_posts(self) -> List[dict]:
        return json.loads(self.state.read_text())["posts"]

    def update_post(self, post_id: str, fields: Dict) -> None:
        data = json.loads(self.state.read_text())
        for p in data["posts"]:
            if p["id"] == post_id:
                p.update({k: v for k, v in fields.items() if k in ("status", "publish_at", "caption")})
        self.state.write_text(json.dumps(data, indent=1))


def make_store(root: Path):
    token, db = os.getenv("NOTION_TOKEN"), os.getenv("NOTION_DATABASE_ID")
    if token and db:
        return NotionStore(token, db), "notion"
    return DemoStore(root / "sample_data" / "posts.json", root / "sample_data" / "demo_state.json"), "demo"
