"""HTMX on My Saved Games: the same URL gives the full page or just the swapped region.

Back and Forward agreement in a real browser is checked manually (Phase 6 step 2 in
the plan); these tests check what the server returns for each kind of request.
"""

import re
from datetime import timedelta

from django.templatetags.static import static
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .factories import make_entry, make_game, make_user

URL = reverse("games:saved_games")
FOOTER = "Game data and cover art from"


class PartialResponseTests(TestCase):
    def setUp(self):
        self.user = make_user("demo_a")
        self.client.force_login(self.user)
        start = timezone.now() - timedelta(days=30)
        # 12 matches, so the query reaches page 2 (Title A to Z: Horror 11 and 12).
        for n in range(1, 13):
            make_entry(
                self.user,
                make_game(f"Horror {n:02d}", themes=[(19, "Horror"), (21, "Survival")]),
                status="playing",
                created_at=start + timedelta(hours=n),
            )
        # Non-matches: wrong status, wrong theme.
        make_entry(
            self.user, make_game("Horror Dropped", themes=[(19, "Horror")]), status="dropped"
        )
        make_entry(self.user, make_game("Portal 2", themes=[(27, "Comedy")]), status="playing")
        self.params = {
            "q": "horror",
            "status": "playing",
            "theme": "19",
            "sort": "title",
            "page": "2",
        }

    def assert_region_reflects_the_query(self, html):
        """Controls and results in the region both show the requested state."""
        region = re.search(r'<div id="saved-games-region".*</div>', html, re.S)
        self.assertIsNotNone(region, "the saved-games region is missing")
        region = region.group(0)
        # Controls.
        self.assertRegex(region, r'<input[^>]*name="q"[^>]*value="horror"')
        self.assertRegex(region, r'<option value="playing" selected>Playing</option>')
        self.assertRegex(region, r'<option value="19" selected>Horror</option>')
        self.assertRegex(region, r'<option value="title" selected>Title A to Z</option>')
        # Exactly those three: Platform Played and Favorite stay on "All".
        self.assertEqual(len(re.findall(r" selected>", region)), 3)
        # Results and page.
        self.assertIn("Page 2 of 2", region)
        rows = re.findall(r'class="fw-semibold" href="[^"]*">([^<]+)</a>', region)
        self.assertEqual(rows, ["Horror 11", "Horror 12"])

    def test_full_page_partial_region_or_full_page_for_a_history_restore(self):
        cases = [
            ("normal request", {}, True),
            ("HX-Request", {"HX-Request": "true"}, False),
            (
                "history restore",
                {"HX-Request": "true", "HX-History-Restore-Request": "true"},
                True,
            ),
        ]
        for label, headers, full_page in cases:
            with self.subTest(label):
                response = self.client.get(URL, self.params, headers=headers)
                html = response.content.decode()

                self.assertEqual(response.status_code, 200)
                self.assert_region_reflects_the_query(html)
                # Every variant says it varies on both headers, so no cache can hand
                # a partial to a full-page request (or the reverse).
                vary = {v.strip() for v in response.headers.get("Vary", "").split(",")}
                self.assertLessEqual({"HX-Request", "HX-History-Restore-Request"}, vary)
                if full_page:
                    self.assertIn("<html", html)
                    self.assertIn(FOOTER, html)
                    self.assertIn("<h1", html)
                    self.assertNotIn("HX-Push-Url", response.headers)
                else:
                    self.assertEqual(
                        response.headers["HX-Push-Url"],
                        f"{URL}?q=horror&status=playing&theme=19&sort=title&page=2",
                    )
                    # Only the region: it is the whole response.
                    self.assertTrue(html.strip().startswith('<div id="saved-games-region"'))
                    self.assertTrue(html.strip().endswith("</div>"))
                    self.assertNotIn("<html", html)
                    self.assertNotIn(FOOTER, html)
                    self.assertNotIn("<h1", html)

    def test_full_page_opts_out_of_htmx_history_snapshots_and_loads_htmx_locally(self):
        full = self.client.get(URL, self.params)
        restore = self.client.get(
            URL, self.params, headers={"HX-Request": "true", "HX-History-Restore-Request": "true"}
        )
        for label, response in [("normal", full), ("history restore", restore)]:
            with self.subTest(label):
                # Outside the region, so it survives every swap.
                self.assertRegex(
                    response.content.decode(),
                    r'hx-history="false"[^>]*>\s*<h1[^>]*>My Saved Games</h1>\s*'
                    r'<div id="saved-games-region"',
                )
                self.assertContains(
                    response, f'src="{static("games/vendor/htmx-2.0.11/htmx.min.js")}" defer'
                )
                self.assertNotContains(response, "unpkg.com")
                self.assertNotContains(response, "cdn.jsdelivr.net")

    def test_pushed_url_is_clean_and_uses_the_page_actually_shown(self):
        hx = {"HX-Request": "true"}
        for label, params, expected in [
            (
                "blank fields, default sort and bad values dropped",
                {
                    "q": "  horror ",
                    "status": "playing",
                    "platform": "",
                    "favorite": "",
                    "theme": "19",
                    "sort": "added",
                    "bogus": "x",
                },
                f"{URL}?q=horror&status=playing&theme=19",
            ),
            (
                "out-of-range page clamped to the last page",
                {**self.params, "page": "99"},
                f"{URL}?q=horror&status=playing&theme=19&sort=title&page=2",
            ),
            (
                "bad page shown as page 1, so no page",
                {**self.params, "page": "0"},
                f"{URL}?q=horror&status=playing&theme=19&sort=title",
            ),
            (
                "unknown sort and malformed theme dropped",
                {"sort": "bogus", "theme": "abc", "page": "1"},
                URL,
            ),
        ]:
            with self.subTest(label):
                response = self.client.get(URL, params, headers=hx)
                self.assertEqual(response.headers["HX-Push-Url"], expected)
