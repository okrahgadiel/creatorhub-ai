"""Engagement analytics, data-driven auto-scheduling, and AI caption suggestions."""
from __future__ import annotations

import json
import os
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# Fallback posting windows (local hour) per platform when there's not enough history yet.
DEFAULT_HOURS = {"Instagram": 12, "TikTok": 19, "YouTube": 15, "X": 9}
MAX_POSTS_PER_DAY = 2


def engagement(p: dict) -> int:
    return int(p.get("likes", 0)) + int(p.get("comments", 0)) + int(p.get("shares", 0))


def engagement_rate(p: dict) -> float:
    imp = int(p.get("impressions", 0))
    return engagement(p) / imp if imp else 0.0


def analytics(posts: List[dict]) -> dict:
    published = [p for p in posts if p.get("status") == "Published"]
    by_platform: Dict[str, dict] = defaultdict(lambda: {"posts": 0, "impressions": 0, "engagements": 0})
    by_pillar: Dict[str, dict] = defaultdict(lambda: {"posts": 0, "impressions": 0, "engagements": 0})
    for p in published:
        for bucket in (by_platform[p["platform"]], by_pillar[p["pillar"]]):
            bucket["posts"] += 1
            bucket["impressions"] += int(p["impressions"])
            bucket["engagements"] += engagement(p)
    for group in (by_platform, by_pillar):
        for v in group.values():
            v["engagement_rate"] = round(v["engagements"] / v["impressions"], 4) if v["impressions"] else 0
    total_imp = sum(int(p["impressions"]) for p in published)
    total_eng = sum(engagement(p) for p in published)
    top = sorted(published, key=engagement_rate, reverse=True)[:5]
    pipeline = defaultdict(int)
    for p in posts:
        pipeline[p.get("status") or "Idea"] += 1
    return {
        "totals": {"published": len(published), "impressions": total_imp, "engagements": total_eng,
                   "engagement_rate": round(total_eng / total_imp, 4) if total_imp else 0},
        "by_platform": dict(by_platform), "by_pillar": dict(by_pillar),
        "top_posts": [{"id": p["id"], "title": p["title"], "platform": p["platform"],
                       "engagement_rate": round(engagement_rate(p), 4)} for p in top],
        "best_hours": best_hours(posts),
        "pipeline": dict(pipeline),
    }


def best_hours(posts: List[dict]) -> Dict[str, int]:
    """Per platform, the publish hour with the highest average engagement rate (min 2 posts of history)."""
    stats: Dict[str, Dict[int, List[float]]] = defaultdict(lambda: defaultdict(list))
    for p in posts:
        if p.get("status") == "Published" and p.get("publish_at"):
            hour = datetime.fromisoformat(p["publish_at"]).hour
            stats[p["platform"]][hour].append(engagement_rate(p))
    out = dict(DEFAULT_HOURS)
    for platform, hours in stats.items():
        if sum(len(v) for v in hours.values()) >= 2:
            out[platform] = max(hours, key=lambda h: sum(hours[h]) / len(hours[h]))
    return out


def auto_schedule(posts: List[dict], start: datetime, days: int = 14) -> List[dict]:
    """Assign publish slots to 'Ready' posts: each platform's best hour, max N posts/day,
    never two posts on the same platform the same day, earliest available day first."""
    hours = best_hours(posts)
    taken_day = defaultdict(int)
    taken_platform_day = set()
    for p in posts:
        if p.get("status") == "Scheduled" and p.get("publish_at"):
            d = datetime.fromisoformat(p["publish_at"]).date()
            taken_day[d] += 1
            taken_platform_day.add((p["platform"], d))
    plan = []
    for p in sorted((p for p in posts if p.get("status") == "Ready"), key=lambda p: p["id"]):
        for offset in range(days):
            day = (start + timedelta(days=offset)).date()
            slot = datetime.combine(day, datetime.min.time()).replace(hour=hours.get(p["platform"], 12))
            if slot <= start or taken_day[day] >= MAX_POSTS_PER_DAY or (p["platform"], day) in taken_platform_day:
                continue
            taken_day[day] += 1
            taken_platform_day.add((p["platform"], day))
            plan.append({"id": p["id"], "title": p["title"], "platform": p["platform"],
                         "publish_at": slot.isoformat(timespec="minutes"), "status": "Scheduled"})
            break
    return plan


HASHTAGS = {"Recipes": ["#recipe", "#foodie", "#homecooking"], "Behind the Scenes": ["#bts", "#kitchenlife"],
            "Community": ["#community", "#localeats"], "Events": ["#event", "#katytx"], "Tips": ["#cookingtips", "#howto"]}
LIMITS = {"X": 280, "Instagram": 2200, "TikTok": 2200, "YouTube": 5000}


def suggest_caption(post: dict, posts: List[dict]) -> dict:
    """Caption suggestion: uses an LLM when OPENAI_API_KEY is set, otherwise a template built from
    what performed best for this pillar. Always enforces the platform's character limit."""
    best = max((p for p in posts if p.get("status") == "Published" and p["pillar"] == post["pillar"]),
               key=engagement_rate, default=None)
    tags = " ".join(HASHTAGS.get(post["pillar"], ["#creator"]))
    caption, source = None, "template"
    if os.getenv("OPENAI_API_KEY"):
        caption = _llm_caption(post, best)
        source = "openai" if caption else source
    if not caption:
        hook = {"TikTok": "Wait for it…", "X": "Quick one:", "YouTube": "New video!", "Instagram": "Save this ✨"}
        caption = f"{hook.get(post['platform'], '')} {post['title']} — tell us what you think in the comments! {tags}".strip()
    limit = LIMITS.get(post["platform"], 2200)
    return {"caption": caption[:limit], "source": source,
            "inspired_by": best["title"] if best else None, "limit": limit}


def _llm_caption(post: dict, best: Optional[dict]) -> Optional[str]:
    prompt = (f"Write one {post['platform']} caption (max {LIMITS.get(post['platform'], 2200)} chars) for a post titled "
              f"'{post['title']}' in the '{post['pillar']}' content pillar. "
              + (f"Our best-performing post in this pillar was '{best['title']}'. " if best else "")
              + "Friendly tone, one call to action, 2-4 hashtags. Return only the caption.")
    body = {"model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"), "temperature": 0.7,
            "messages": [{"role": "user", "content": prompt}]}
    req = urllib.request.Request("https://api.openai.com/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())["choices"][0]["message"]["content"].strip()
    except Exception:
        return None
