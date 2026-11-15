"""Removing an entry after a confirmation page (stories 8, 81, 82, 83, 84)."""

from django.test import TestCase
from django.urls import reverse

from games.models import Entry, Game

from .factories import csrf_client, make_entry, make_game, make_user


def delete_url(entry_id):
    return reverse("games:entry_delete", args=[entry_id])


class EntryDeletePostTests(TestCase):
    def setUp(self):
        self.owner = make_user("demo_a")
        self.other = make_user("demo_b")
        self.game = make_game("The Witcher 3: Wild Hunt")
        self.entry = make_entry(self.owner, self.game, notes="Owner's notes")
        self.other_entry = make_entry(self.other, self.game, notes="Other user's notes")

    def test_owner_post_removes_only_their_entry_and_keeps_the_shared_game(self):
        self.client.force_login(self.owner)

        response = self.client.post(delete_url(self.entry.pk), follow=True)

        self.assertRedirects(response, reverse("games:saved_games"))
        self.assertContains(response, "Removed The Witcher 3: Wild Hunt from My Games.")
        self.assertFalse(Entry.objects.filter(pk=self.entry.pk).exists())
        self.assertTrue(Game.objects.filter(pk=self.game.pk).exists())
        other_entry = Entry.objects.get(pk=self.other_entry.pk)
        self.assertEqual(other_entry.owner, self.other)
        self.assertEqual(other_entry.notes, "Other user's notes")


class EntryDeleteConfirmationTests(TestCase):
    def setUp(self):
        self.user = make_user("demo_a")
        self.client.force_login(self.user)
        self.entry = make_entry(self.user, make_game("Dead Space"), notes="Keep me")

    def test_get_only_shows_the_confirmation_page(self):
        response = self.client.get(delete_url(self.entry.pk))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Remove Dead Space?")
        self.assertContains(
            response, "Your status, rating, notes and hours played for it will be deleted."
        )
        self.assertContains(
            response,
            '<button type="submit" class="btn btn-danger">Remove from My Games</button>',
            html=True,
        )
        self.assertContains(response, f'action="{delete_url(self.entry.pk)}"')
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertTrue(Entry.objects.filter(pk=self.entry.pk, notes="Keep me").exists())

    def test_cancel_links_to_the_entry_detail_page(self):
        detail = reverse("games:entry_detail", args=[self.entry.pk])
        page = self.client.get(delete_url(self.entry.pk))
        self.assertContains(
            page,
            f'<a href="{detail}" class="btn btn-outline-secondary" '
            'data-testid="cancel-delete">Cancel</a>',
            html=True,
        )

        response = self.client.get(detail)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dead Space")
        self.assertTrue(Entry.objects.filter(pk=self.entry.pk).exists())

    def test_detail_page_links_to_edit_and_remove(self):
        response = self.client.get(reverse("games:entry_detail", args=[self.entry.pk]))
        edit = reverse("games:entry_edit", args=[self.entry.pk])
        self.assertContains(response, f'href="{edit}"')
        self.assertContains(response, f'href="{delete_url(self.entry.pk)}"')

    def test_post_without_a_csrf_token_is_403_and_deletes_nothing(self):
        client, _token = csrf_client(self.user, delete_url(self.entry.pk))

        response = client.post(delete_url(self.entry.pk))

        self.assertEqual(response.status_code, 403)
        self.assertTrue(Entry.objects.filter(pk=self.entry.pk).exists())

    def test_post_with_a_valid_csrf_token_deletes(self):
        client, token = csrf_client(self.user, delete_url(self.entry.pk))

        response = client.post(delete_url(self.entry.pk), {"csrfmiddlewaretoken": token})

        self.assertRedirects(response, reverse("games:saved_games"))
        self.assertFalse(Entry.objects.filter(pk=self.entry.pk).exists())

    def test_other_methods_are_rejected(self):
        response = self.client.put(delete_url(self.entry.pk))
        self.assertEqual(response.status_code, 405)
        self.assertTrue(Entry.objects.filter(pk=self.entry.pk).exists())

    def test_signed_out_visitor_is_redirected_and_nothing_is_deleted(self):
        self.client.logout()
        url = delete_url(self.entry.pk)
        self.assertRedirects(self.client.get(url), f"{reverse('login')}?next={url}")
        self.assertRedirects(self.client.post(url), f"{reverse('login')}?next={url}")
        self.assertTrue(Entry.objects.filter(pk=self.entry.pk).exists())


class EntryDeleteIsolationTests(TestCase):
    def setUp(self):
        self.owner = make_user("demo_a")
        self.other = make_user("demo_b")
        self.game = make_game("Silent Hill 2")
        self.entry = make_entry(self.owner, self.game, notes="Owner's notes", rating=10)
        self.other_entry = make_entry(self.other, make_game("Celeste"))

    def test_another_users_entry_returns_404_for_get(self):
        self.client.force_login(self.other)
        response = self.client.get(delete_url(self.entry.pk))
        self.assertEqual(response.status_code, 404)
        self.assertNotContains(response, "Silent Hill 2", status_code=404)

    def test_another_users_entry_returns_404_for_a_csrf_valid_post_and_is_unchanged(self):
        client, token = csrf_client(self.other, delete_url(self.other_entry.pk))

        response = client.post(delete_url(self.entry.pk), {"csrfmiddlewaretoken": token})

        self.assertEqual(response.status_code, 404)
        entry = Entry.objects.get(pk=self.entry.pk)
        self.assertEqual(
            (entry.owner, entry.notes, entry.rating), (self.owner, "Owner's notes", 10)
        )
        self.assertTrue(Game.objects.filter(pk=self.game.pk).exists())
        # The same token still works on B's own entry, so the 404 wasn't a CSRF failure.
        own = client.post(delete_url(self.other_entry.pk), {"csrfmiddlewaretoken": token})
        self.assertRedirects(own, reverse("games:saved_games"))

    def test_a_missing_entry_returns_404_for_get_and_post(self):
        self.client.force_login(self.other)
        missing_id = Entry.objects.order_by("-pk").first().pk + 1000
        self.assertEqual(self.client.get(delete_url(missing_id)).status_code, 404)
        self.assertEqual(self.client.post(delete_url(missing_id)).status_code, 404)
        self.assertEqual(Entry.objects.count(), 2)
