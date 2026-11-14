"""Base layout: IGDB attribution, navigation and local static assets (stories 5, 115)."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()

FOOTER_LINK = '<a href="https://www.igdb.com/" rel="noopener">IGDB.com</a>'


class FooterTests(TestCase):
    def assert_footer(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Game data and cover art from")
        self.assertContains(response, FOOTER_LINK, html=True)

    def test_footer_on_public_pages(self):
        for name in ("login", "signup"):
            with self.subTest(page=name):
                self.assert_footer(self.client.get(reverse(name)))

    def test_footer_on_protected_pages(self):
        self.client.force_login(User.objects.create_user("player", password="x"))
        for name in ("games:saved_games", "games:search"):
            with self.subTest(page=name):
                self.assert_footer(self.client.get(reverse(name)))


class NavigationTests(TestCase):
    def test_signed_in_nav_has_links_username_and_post_logout(self):
        self.client.force_login(User.objects.create_user("player", password="x"))
        response = self.client.get(reverse("games:saved_games"))

        self.assertContains(response, f'href="{reverse("games:saved_games")}"')
        self.assertContains(response, f'href="{reverse("games:search")}"')
        self.assertContains(response, "<strong>player</strong>", html=True)
        self.assertContains(response, f'<form method="post" action="{reverse("logout")}"')

    def test_signed_out_nav_offers_login_and_signup(self):
        response = self.client.get(reverse("login"))
        self.assertContains(response, f'href="{reverse("signup")}"')
        self.assertNotContains(response, f'action="{reverse("logout")}"')


class StaticAssetTests(TestCase):
    def test_bootstrap_is_served_from_local_static_files(self):
        response = self.client.get(reverse("login"))
        self.assertContains(response, "/static/games/vendor/bootstrap-5.3.8/css/bootstrap.min.css")
        self.assertContains(
            response, "/static/games/vendor/bootstrap-5.3.8/js/bootstrap.bundle.min.js"
        )
        self.assertNotContains(response, "cdn.")
