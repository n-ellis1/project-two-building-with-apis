"""Saved-games paging helper and the owner-scoped entry helper (stories 7, 8, 63, 64)."""

from django.core.paginator import Paginator
from django.http import Http404
from django.test import SimpleTestCase, TestCase

from games.queries import PAGE_SIZE, get_owned_entry_or_404, owned_entries, parse_page

from .factories import make_entry, make_user


class ParsePageTests(SimpleTestCase):
    """The prototype verification table: 27 items, 10 per page, so 3 pages."""

    def setUp(self):
        self.paginator = Paginator(range(27), PAGE_SIZE)

    def page_for(self, raw):
        return self.paginator.get_page(parse_page(raw)).number

    def test_anything_that_is_not_a_positive_integer_becomes_page_1(self):
        for raw in (None, "", "abc", "2.5", "0", "-1"):
            with self.subTest(page=raw):
                self.assertEqual(parse_page(raw), 1)
                self.assertEqual(self.page_for(raw), 1)

    def test_a_valid_page_is_kept(self):
        self.assertEqual(parse_page("2"), 2)
        self.assertEqual(self.page_for("2"), 2)

    def test_a_page_past_the_end_shows_the_last_page(self):
        self.assertEqual(self.page_for("99"), 3)


class OwnedEntryTests(TestCase):
    def setUp(self):
        self.owner = make_user("demo_a")
        self.other = make_user("demo_b")
        self.entry = make_entry(self.owner)

    def test_the_owner_gets_their_entry(self):
        self.assertEqual(get_owned_entry_or_404(self.owner, self.entry.pk), self.entry)

    def test_another_users_entry_is_404_like_a_missing_id(self):
        for user, entry_id in [(self.other, self.entry.pk), (self.owner, 999_999)]:
            with self.subTest(user=user.username, entry_id=entry_id):
                with self.assertRaises(Http404):
                    get_owned_entry_or_404(user, entry_id)

    def test_owned_entries_contains_only_the_users_entries(self):
        make_entry(self.other)
        self.assertEqual(list(owned_entries(self.owner)), [self.entry])
