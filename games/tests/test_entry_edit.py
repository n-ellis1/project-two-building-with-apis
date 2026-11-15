"""Editing an entry's tracking fields with the shared validation (stories 8, 37-44, 80)."""

from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from games.models import Entry

from .factories import csrf_client, make_entry, make_game, make_user


def edit_url(entry_id):
    return reverse("games:entry_edit", args=[entry_id])


def detail_url(entry_id):
    return reverse("games:entry_detail", args=[entry_id])


def form_data(**overrides):
    """A complete, valid edit form submission (blank optional fields)."""
    data = {
        "status": Entry.Status.WANT_TO_PLAY,
        "rating": "",
        "platform_played": "",
        "start_date": "",
        "finish_date": "",
        "hours_played": "",
        "notes": "",
    }
    data.update(overrides)
    return {key: value for key, value in data.items() if value is not None}


class EntryEditFormPageTests(TestCase):
    def setUp(self):
        self.user = make_user("demo_a")
        self.client.force_login(self.user)
        self.game = make_game("Hades", platforms=["Nintendo Switch", "PC (Microsoft Windows)"])

    def test_form_shows_the_tracking_fields_and_the_games_platforms(self):
        entry = make_entry(self.user, self.game, platform_played="Nintendo Switch")

        response = self.client.get(edit_url(entry.pk))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Edit Hades")
        for name in (
            "status",
            "favorite",
            "rating",
            "platform_played",
            "start_date",
            "finish_date",
            "hours_played",
            "notes",
        ):
            with self.subTest(field=name):
                self.assertContains(response, f'name="{name}"')
        self.assertContains(response, '<option value="">Not set</option>', html=True)
        self.assertContains(
            response, '<option value="Nintendo Switch" selected>Nintendo Switch</option>', html=True
        )
        self.assertContains(
            response,
            '<option value="PC (Microsoft Windows)">PC (Microsoft Windows)</option>',
            html=True,
        )
        self.assertContains(response, '<option value="" selected>Not rated</option>', html=True)
        self.assertContains(response, f'href="{detail_url(entry.pk)}"')
        self.assertContains(response, 'data-testid="cancel-edit"')

    def test_a_stale_stored_platform_is_offered_and_selected(self):
        entry = make_entry(self.user, self.game, platform_played="PlayStation Vita")

        response = self.client.get(edit_url(entry.pk))

        self.assertContains(
            response,
            '<option value="PlayStation Vita" selected>'
            "PlayStation Vita (no longer listed for this game)</option>",
            html=True,
        )

    def test_signed_out_visitor_is_redirected_to_login(self):
        entry = make_entry(self.user, self.game)
        self.client.logout()
        url = edit_url(entry.pk)
        self.assertRedirects(self.client.get(url), f"{reverse('login')}?next={url}")


class EntryEditSaveTests(TestCase):
    def setUp(self):
        self.user = make_user("demo_a")
        self.client.force_login(self.user)
        self.game = make_game("Hades", platforms=["Nintendo Switch", "PC (Microsoft Windows)"])
        self.entry = make_entry(self.user, self.game)

    def test_every_field_saves_and_shows_on_the_detail_page(self):
        response = self.client.post(
            edit_url(self.entry.pk),
            form_data(
                status=Entry.Status.PLAYING,
                favorite="on",
                rating="8",
                platform_played="Nintendo Switch",
                start_date="2026-10-01",
                finish_date="2026-10-20",
                hours_played="32.5",
                notes="Reached Elysium.",
            ),
            follow=True,
        )

        self.assertRedirects(response, detail_url(self.entry.pk))
        self.assertContains(response, "Saved your changes to Hades.")
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.status, Entry.Status.PLAYING)
        self.assertTrue(self.entry.favorite)
        self.assertEqual(self.entry.rating, 8)
        self.assertEqual(self.entry.platform_played, "Nintendo Switch")
        self.assertEqual(self.entry.start_date, date(2026, 10, 1))
        self.assertEqual(self.entry.finish_date, date(2026, 10, 20))
        self.assertEqual(self.entry.hours_played, Decimal("32.5"))
        self.assertEqual(self.entry.notes, "Reached Elysium.")
        for text in ("Playing", "8/10", "Nintendo Switch", "October 1, 2026", "32.5"):
            with self.subTest(text=text):
                self.assertContains(response, text)

    def test_all_five_statuses_save(self):
        for status in Entry.Status.values:
            with self.subTest(status=status):
                response = self.client.post(edit_url(self.entry.pk), form_data(status=status))
                self.assertRedirects(response, detail_url(self.entry.pk))
                self.entry.refresh_from_db()
                self.assertEqual(self.entry.status, status)

    def test_blank_fields_clear_rating_favorite_platform_dates_and_hours(self):
        Entry.objects.filter(pk=self.entry.pk).update(
            favorite=True,
            rating=7,
            platform_played="Nintendo Switch",
            start_date=date(2026, 1, 1),
            finish_date=date(2026, 1, 2),
            hours_played=Decimal("3.0"),
            notes="old",
        )

        response = self.client.post(edit_url(self.entry.pk), form_data())

        self.assertRedirects(response, detail_url(self.entry.pk))
        self.entry.refresh_from_db()
        self.assertFalse(self.entry.favorite)
        self.assertIsNone(self.entry.rating)
        self.assertEqual(self.entry.platform_played, "")
        self.assertIsNone(self.entry.start_date)
        self.assertIsNone(self.entry.finish_date)
        self.assertIsNone(self.entry.hours_played)
        self.assertEqual(self.entry.notes, "")

    def test_either_date_may_be_blank_for_any_status(self):
        for status in (Entry.Status.COMPLETED, Entry.Status.DROPPED):
            for start, finish in (("", "2026-10-20"), ("2026-10-01", "")):
                with self.subTest(status=status, start=start, finish=finish):
                    response = self.client.post(
                        edit_url(self.entry.pk),
                        form_data(status=status, start_date=start, finish_date=finish),
                    )
                    self.assertRedirects(response, detail_url(self.entry.pk))

    def assert_rejected(self, data, field, message):
        before = Entry.objects.get(pk=self.entry.pk)
        response = self.client.post(edit_url(self.entry.pk), data)
        self.assertEqual(response.status_code, 200)
        self.assertIn(message, response.context["form"].errors[field])
        self.assertContains(response, message.replace("'", "&#x27;"))
        after = Entry.objects.get(pk=self.entry.pk)
        self.assertEqual(after.updated_at, before.updated_at)
        self.assertEqual(after.notes, before.notes)

    def test_finish_before_start_is_a_form_error_and_nothing_saves(self):
        self.assert_rejected(
            form_data(start_date="2026-10-20", finish_date="2026-10-01", notes="changed"),
            "finish_date",
            "Finish date can't be before the start date.",
        )

    def test_negative_hours_are_rejected(self):
        self.assert_rejected(
            form_data(hours_played="-1", notes="changed"),
            "hours_played",
            "Ensure this value is greater than or equal to 0.",
        )

    def test_ratings_outside_1_to_10_are_rejected(self):
        for rating in ("0", "11"):
            with self.subTest(rating=rating):
                response = self.client.post(
                    edit_url(self.entry.pk), form_data(rating=rating, notes="changed")
                )
                self.assertEqual(response.status_code, 200)
                self.assertIn("rating", response.context["form"].errors)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.notes, "")

    def test_a_platform_the_game_does_not_list_is_rejected(self):
        self.assert_rejected(
            form_data(platform_played="Nintendo 64", notes="changed"),
            "platform_played",
            "Choose one of this game's platforms, or leave it blank.",
        )


class StalePlatformEditTests(TestCase):
    """Story 80: a stale stored platform never blocks editing other fields."""

    def setUp(self):
        self.user = make_user("demo_a")
        self.client.force_login(self.user)
        game = make_game("Resident Evil 2", platforms=["PlayStation 4", "PC (Microsoft Windows)"])
        self.entry = make_entry(self.user, game, platform_played="PlayStation", notes="Leon A")

    def test_notes_can_change_while_the_stale_platform_stays(self):
        response = self.client.post(
            edit_url(self.entry.pk),
            form_data(status=Entry.Status.PLAYING, platform_played="PlayStation", notes="Claire B"),
        )

        self.assertRedirects(response, detail_url(self.entry.pk))
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.notes, "Claire B")
        self.assertEqual(self.entry.platform_played, "PlayStation")

    def test_it_cannot_change_to_an_unlisted_platform(self):
        response = self.client.post(
            edit_url(self.entry.pk),
            form_data(platform_played="Sega Saturn", notes="Claire B"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["form"].errors["platform_played"],
            ["Choose one of this game's platforms, or leave it blank."],
        )
        self.entry.refresh_from_db()
        self.assertEqual((self.entry.platform_played, self.entry.notes), ("PlayStation", "Leon A"))

    def test_once_changed_to_a_current_platform_the_stale_value_is_no_longer_allowed(self):
        self.client.post(edit_url(self.entry.pk), form_data(platform_played="PlayStation 4"))
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.platform_played, "PlayStation 4")

        response = self.client.post(
            edit_url(self.entry.pk), form_data(platform_played="PlayStation")
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("platform_played", response.context["form"].errors)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.platform_played, "PlayStation 4")


class EntryEditIsolationTests(TestCase):
    def setUp(self):
        self.owner = make_user("demo_a")
        self.other = make_user("demo_b")
        self.entry = make_entry(
            self.owner,
            make_game("Alien: Isolation", platforms=["PC (Microsoft Windows)"]),
            notes="Owner's notes",
        )
        self.other_entry = make_entry(self.other, make_game("Celeste"))

    def test_another_users_entry_returns_404_for_get(self):
        self.client.force_login(self.other)
        response = self.client.get(edit_url(self.entry.pk))
        self.assertEqual(response.status_code, 404)
        self.assertNotContains(response, "Alien: Isolation", status_code=404)

    def test_another_users_entry_returns_404_for_a_csrf_valid_post_and_is_unchanged(self):
        client, token = csrf_client(self.other, edit_url(self.other_entry.pk))
        before = Entry.objects.get(pk=self.entry.pk)

        response = client.post(
            edit_url(self.entry.pk),
            form_data(csrfmiddlewaretoken=token, status=Entry.Status.DROPPED, notes="hijacked"),
        )

        self.assertEqual(response.status_code, 404)
        after = Entry.objects.get(pk=self.entry.pk)
        self.assertEqual(after.owner, self.owner)
        self.assertEqual(after.status, before.status)
        self.assertEqual(after.notes, "Owner's notes")
        self.assertEqual(after.updated_at, before.updated_at)

    def test_the_same_token_works_on_the_users_own_entry(self):
        """Proves the token in the 404 test above is valid, so 404 isn't really a CSRF 403."""
        client, token = csrf_client(self.other, edit_url(self.other_entry.pk))
        response = client.post(
            edit_url(self.other_entry.pk), form_data(csrfmiddlewaretoken=token, notes="mine")
        )
        self.assertRedirects(response, detail_url(self.other_entry.pk))

    def test_a_missing_entry_returns_404(self):
        self.client.force_login(self.other)
        missing_id = Entry.objects.order_by("-pk").first().pk + 1000
        self.assertEqual(self.client.get(edit_url(missing_id)).status_code, 404)
