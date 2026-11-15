"""Entry detail page: owner-only, large cover, game details and tracking data (8, 69, 77)."""

import re
from datetime import date, timedelta
from decimal import Decimal

from django.templatetags.static import static
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from games.covers import PLACEHOLDER_STATIC_PATH, cover_url
from games.models import Entry, GameCategory, Genre, Theme

from .factories import make_entry, make_game, make_user
from .test_covers import ImgCollector


def detail_url(entry_id):
    return reverse("games:entry_detail", args=[entry_id])


def cover_imgs(response):
    parser = ImgCollector()
    parser.feed(response.content.decode())
    return [img for img in parser.imgs if "game-cover" in img.get("class", "")]


class EntryDetailAccessTests(TestCase):
    def setUp(self):
        self.owner = make_user("demo_a")
        self.other = make_user("demo_b")
        self.entry = make_entry(self.owner, make_game("Alien: Isolation"))

    def test_owner_gets_200(self):
        self.client.force_login(self.owner)
        response = self.client.get(detail_url(self.entry.pk))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alien: Isolation")

    def test_another_users_entry_and_a_missing_entry_both_return_404(self):
        missing_id = Entry.objects.order_by("-pk").first().pk + 1000
        self.client.force_login(self.other)
        for entry_id in (self.entry.pk, missing_id):
            with self.subTest(entry_id=entry_id):
                response = self.client.get(detail_url(entry_id))
                self.assertEqual(response.status_code, 404)
                self.assertNotContains(response, "Alien: Isolation", status_code=404)

    def test_signed_out_visitor_is_redirected_to_login(self):
        url = detail_url(self.entry.pk)
        self.assertRedirects(self.client.get(url), f"{reverse('login')}?next={url}")


class ReturnToSavedGamesPageTests(TestCase):
    """B1: the detail page's My Saved Games link returns to the page it was opened from."""

    def setUp(self):
        self.user = make_user("demo_a")
        self.client.force_login(self.user)
        start = timezone.now() - timedelta(days=30)
        # 12 entries: the oldest two land on page 2 (newest first, 10 per page).
        self.entries = [
            make_entry(self.user, make_game(f"Game {n:02d}"), created_at=start + timedelta(hours=n))
            for n in range(1, 13)
        ]
        self.oldest = self.entries[0]

    def return_href(self, response):
        self.assertContains(response, 'data-testid="saved-games-return"')
        match = re.search(
            r'href="([^"]*)"[^>]*data-testid="saved-games-return"', response.content.decode()
        )
        self.assertIsNotNone(match)
        return match.group(1)

    def test_opening_an_entry_from_page_2_returns_to_page_2(self):
        list_page = self.client.get(reverse("games:saved_games"), {"page": "2"})
        detail_link = f"{detail_url(self.oldest.pk)}?page=2"
        self.assertContains(list_page, f'href="{detail_link}"')

        response = self.client.get(detail_link)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.return_href(response), f"{reverse('games:saved_games')}?page=2")

    def test_direct_entry_with_no_originating_page_returns_to_page_1(self):
        response = self.client.get(detail_url(self.oldest.pk))
        self.assertEqual(self.return_href(response), reverse("games:saved_games"))

    def test_invalid_or_unsafe_page_values_return_to_page_1(self):
        for raw in ("", "1", "0", "-1", "abc", "2.5", "https://example.com/", '2"><script>'):
            with self.subTest(page=raw):
                response = self.client.get(detail_url(self.oldest.pk), {"page": raw})
                self.assertEqual(self.return_href(response), reverse("games:saved_games"))
                self.assertNotContains(response, "example.com")
                self.assertNotContains(response, "<script>")

    def test_page_1_list_links_carry_no_page(self):
        newest = self.entries[-1]
        response = self.client.get(reverse("games:saved_games"))
        self.assertContains(response, f'href="{detail_url(newest.pk)}"')
        self.assertNotContains(response, f'href="{detail_url(newest.pk)}?page=')

    def test_another_users_entry_is_still_404_with_a_page(self):
        self.client.force_login(make_user("demo_b"))
        response = self.client.get(detail_url(self.oldest.pk), {"page": "2"})
        self.assertEqual(response.status_code, 404)


class EntryDetailContentTests(TestCase):
    def setUp(self):
        self.user = make_user("player")
        self.client.force_login(self.user)

    def test_large_cover_is_264_by_374_with_no_srcset_and_the_fallback_marker(self):
        entry = make_entry(self.user, make_game("Dark Souls III", cover_image_id="co1vcf"))

        imgs = cover_imgs(self.client.get(detail_url(entry.pk)))

        self.assertEqual(len(imgs), 1)
        img = imgs[0]
        self.assertEqual(img["src"], cover_url("co1vcf", "large"))
        self.assertNotIn("srcset", img)
        self.assertEqual(img["width"], "264")
        self.assertEqual(img["height"], "374")
        self.assertEqual(img["loading"], "lazy")
        self.assertEqual(img["alt"], "Dark Souls III")
        self.assertEqual(img["data-cover-placeholder"], static(PLACEHOLDER_STATIC_PATH))

    def test_no_cover_id_shows_the_large_placeholder(self):
        entry = make_entry(self.user, make_game("Scuffed Rocket League", cover_image_id=""))

        (img,) = cover_imgs(self.client.get(detail_url(entry.pk)))

        self.assertEqual(img["src"], static(PLACEHOLDER_STATIC_PATH))
        self.assertNotIn("srcset", img)
        self.assertEqual((img["width"], img["height"]), ("264", "374"))

    def test_shows_game_details_tracking_fields_and_igdb_attribution(self):
        game = make_game(
            "Dark Souls III: The Ringed City",
            platforms=["PlayStation 4", "Xbox One"],
            summary="The final chapter.",
            first_release_date=date(2017, 3, 28),
            game_category=GameCategory.EXPANSION,
            igdb_url="https://www.igdb.com/games/dark-souls-iii-the-ringed-city",
        )
        game.genres.add(Genre.objects.create(igdb_id=12, name="Role-playing (RPG)"))
        game.themes.add(Theme.objects.create(igdb_id=17, name="Fantasy"))
        entry = make_entry(
            self.user,
            game,
            status=Entry.Status.COMPLETED,
            favorite=True,
            rating=9,
            notes="Gael fight was brutal.",
            platform_played="PlayStation 4",
            start_date=date(2026, 3, 1),
            finish_date=date(2026, 3, 9),
            hours_played=Decimal("14.5"),
        )

        response = self.client.get(detail_url(entry.pk))

        for text in (
            "Dark Souls III: The Ringed City",
            "The final chapter.",
            "March 28, 2017",
            "PlayStation 4, Xbox One",
            "Role-playing (RPG)",
            "Fantasy",
            ">Expansion</span>",
            "Completed",
            "★ Favorite",
            "9/10",
            "Gael fight was brutal.",
            "March 1, 2026",
            "March 9, 2026",
            "14.5",
            "Data from IGDB",
            'href="https://www.igdb.com/games/dark-souls-iii-the-ringed-city"',
        ):
            with self.subTest(text=text):
                self.assertContains(response, text)

    def test_blank_tracking_fields_show_not_set(self):
        entry = make_entry(self.user, make_game("Celeste"))

        response = self.client.get(detail_url(entry.pk))

        self.assertContains(response, "Want to Play")
        self.assertContains(response, "Not set")
        self.assertNotContains(response, "★ Favorite")
        self.assertNotContains(response, 'data-testid="category-badge"')
