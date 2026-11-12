import json
import unittest
from datetime import datetime
from unittest import mock

from creatorhub.insights import analytics, auto_schedule, best_hours, engagement_rate, suggest_caption
from creatorhub.notion import NotionStore, page_to_post, post_to_properties


def post(pid, platform="Instagram", status="Published", hour=12, imp=1000, likes=50, pillar="Recipes"):
    return {"id": pid, "title": pid, "platform": platform, "pillar": pillar, "status": status,
            "publish_at": f"2026-10-01T{hour:02d}:00:00" if status == "Published" else None,
            "impressions": imp, "likes": likes, "comments": 0, "shares": 0, "caption": ""}


class AnalyticsTests(unittest.TestCase):
    def test_engagement_rate_handles_zero_impressions(self):
        self.assertEqual(engagement_rate(post("a", imp=0)), 0.0)

    def test_totals_and_breakdowns(self):
        a = analytics([post("a", imp=1000, likes=100), post("b", platform="TikTok", imp=1000, likes=50),
                       post("c", status="Idea")])
        self.assertEqual(a["totals"]["published"], 2)
        self.assertAlmostEqual(a["totals"]["engagement_rate"], 0.075)
        self.assertEqual(a["top_posts"][0]["id"], "a")
        self.assertEqual(a["pipeline"], {"Published": 2, "Idea": 1})

    def test_best_hour_learned_from_history(self):
        posts = [post("a", hour=9, likes=10), post("b", hour=18, likes=200), post("c", hour=18, likes=150)]
        self.assertEqual(best_hours(posts)["Instagram"], 18)


class SchedulerTests(unittest.TestCase):
    def test_one_post_per_platform_per_day_and_daily_cap(self):
        posts = [post(f"r{i}", platform="TikTok", status="Ready") for i in range(3)]
        plan = auto_schedule(posts, datetime(2026, 11, 11, 8))
        days = [p["publish_at"][:10] for p in plan]
        self.assertEqual(len(plan), 3)
        self.assertEqual(len(set(days)), 3)  # never two TikToks on the same day

    def test_respects_existing_scheduled_posts(self):
        existing = post("s", platform="X", status="Scheduled")
        existing["publish_at"] = "2026-11-11T09:00"
        plan = auto_schedule([existing, post("r", platform="X", status="Ready")], datetime(2026, 11, 11, 8))
        self.assertEqual(plan[0]["publish_at"][:10], "2026-11-12")

    def test_never_schedules_in_the_past(self):
        plan = auto_schedule([post("r", platform="X", status="Ready")], datetime(2026, 11, 11, 23))
        self.assertGreater(plan[0]["publish_at"], "2026-11-11T23")


class CaptionTests(unittest.TestCase):
    @mock.patch.dict("os.environ", {"OPENAI_API_KEY": ""})
    def test_template_caption_respects_platform_limit(self):
        p = post("x", platform="X", status="Ready")
        p["title"] = "a" * 400
        s = suggest_caption(p, [post("best")])
        self.assertLessEqual(len(s["caption"]), 280)
        self.assertEqual(s["inspired_by"], "best")


class NotionTests(unittest.TestCase):
    PAGE = {"id": "page-1", "properties": {
        "Name": {"title": [{"plain_text": "Kitchen tour"}]},
        "Platform": {"select": {"name": "TikTok"}}, "Pillar": {"select": {"name": "Recipes"}},
        "Status": {"status": {"name": "Ready"}}, "Publish Date": {"date": None},
        "Impressions": {"number": 1200}, "Likes": {"number": 80}, "Comments": {"number": None},
        "Shares": {"number": 4}, "Caption": {"rich_text": []}}}

    def test_page_to_post_maps_properties(self):
        p = page_to_post(self.PAGE)
        self.assertEqual((p["title"], p["platform"], p["status"], p["impressions"], p["comments"]),
                         ("Kitchen tour", "TikTok", "Ready", 1200, 0))

    def test_post_to_properties(self):
        props = post_to_properties({"status": "Scheduled", "publish_at": "2026-11-12T09:00"})
        self.assertEqual(props["Status"]["status"]["name"], "Scheduled")
        self.assertEqual(props["Publish Date"]["date"]["start"], "2026-11-12T09:00")

    def test_list_posts_follows_pagination(self):
        pages = [{"results": [self.PAGE], "has_more": True, "next_cursor": "c2"},
                 {"results": [self.PAGE], "has_more": False, "next_cursor": None}]
        calls = []

        def fake(method, path, body=None):
            calls.append(body)
            return pages[len(calls) - 1]

        store = NotionStore("secret", "db")
        with mock.patch.object(store, "_request", side_effect=fake):
            self.assertEqual(len(store.list_posts()), 2)
        self.assertEqual(calls[1]["start_cursor"], "c2")


if __name__ == "__main__":
    unittest.main()
