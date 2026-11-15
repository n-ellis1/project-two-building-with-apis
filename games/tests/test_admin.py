"""Admin: imported IGDB data is read-only, entry tracking fields are editable (stories 9-11)."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from games.models import Entry, Genre, Platform, Theme

from .factories import make_entry, make_game, make_user

User = get_user_model()


class AdminTests(TestCase):
    def setUp(self):
        admin_user = User.objects.create_superuser("admin", password="admin-test-not-real")
        self.client.force_login(admin_user)
        self.game = make_game("Celeste", platforms=["PC (Microsoft Windows)"])
        self.entry = make_entry(make_user("player"), self.game)

    def test_game_change_page_is_view_only(self):
        url = reverse("admin:games_game_change", args=[self.game.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Celeste")
        self.assertNotContains(response, 'name="name"')
        self.assertNotContains(response, 'type="submit" value="Save"')

        response = self.client.post(url, {"name": "Changed"})
        self.assertEqual(response.status_code, 403)
        self.game.refresh_from_db()
        self.assertEqual(self.game.name, "Celeste")

    def test_imported_data_cannot_be_added_or_deleted(self):
        for model in ("game", "platform", "genre", "theme"):
            with self.subTest(model=model):
                self.assertEqual(
                    self.client.get(reverse(f"admin:games_{model}_add")).status_code, 403
                )
        url = reverse("admin:games_game_delete", args=[self.game.pk])
        self.assertEqual(self.client.post(url, {"post": "yes"}).status_code, 403)

    def test_platform_genre_and_theme_change_pages_are_view_only(self):
        items = [
            Platform.objects.get(name="PC (Microsoft Windows)"),
            Genre.objects.create(igdb_id=31, name="Adventure"),
            Theme.objects.create(igdb_id=19, name="Horror"),
        ]
        for item in items:
            with self.subTest(model=type(item).__name__):
                name = type(item).__name__.lower()
                response = self.client.get(reverse(f"admin:games_{name}_change", args=[item.pk]))
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, 'name="name"')

    def test_entry_tracking_fields_are_editable_but_owner_and_game_are_not(self):
        url = reverse("admin:games_entry_change", args=[self.entry.pk])
        response = self.client.get(url)
        self.assertContains(response, 'name="status"')
        self.assertContains(response, 'name="notes"')
        self.assertNotContains(response, 'name="owner"')
        self.assertNotContains(response, 'name="game"')

        response = self.client.post(
            url,
            {"status": Entry.Status.PLAYING, "notes": "Debug note", "rating": "7"},
        )
        self.assertRedirects(response, reverse("admin:games_entry_changelist"))
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.status, Entry.Status.PLAYING)
        self.assertEqual(self.entry.rating, 7)
        self.assertEqual(self.entry.game, self.game)

    def test_entry_admin_rejects_an_out_of_range_rating(self):
        url = reverse("admin:games_entry_change", args=[self.entry.pk])
        response = self.client.post(url, {"status": Entry.Status.PLAYING, "rating": "11"})
        self.assertEqual(response.status_code, 200)
        self.entry.refresh_from_db()
        self.assertIsNone(self.entry.rating)
