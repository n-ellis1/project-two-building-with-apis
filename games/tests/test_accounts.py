"""Sign-up, login, logout and the home redirect (PRD stories 1-5)."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()
PASSWORD = "correct-horse-battery-42"


class HomeRedirectTests(TestCase):
    def test_home_sends_signed_in_users_to_saved_games_and_others_to_login(self):
        response = self.client.get(reverse("games:home"))
        self.assertRedirects(response, reverse("login"))

        user = User.objects.create_user("player", password=PASSWORD)
        self.client.force_login(user)
        response = self.client.get(reverse("games:home"))
        self.assertRedirects(response, reverse("games:saved_games"))


class SignupTests(TestCase):
    def test_signup_creates_user_signs_them_in_and_lands_on_saved_games(self):
        response = self.client.post(
            reverse("signup"),
            {"username": "newplayer", "password1": PASSWORD, "password2": PASSWORD},
        )

        self.assertRedirects(response, reverse("games:saved_games"))
        user = User.objects.get(username="newplayer")
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_invalid_signup_shows_errors_and_creates_nobody(self):
        response = self.client.post(
            reverse("signup"),
            {"username": "newplayer", "password1": PASSWORD, "password2": "different"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="newplayer").exists())
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(response, "is-invalid")


class LoginTests(TestCase):
    def setUp(self):
        User.objects.create_user("player", password=PASSWORD)

    def login(self, **extra):
        data = {"username": "player", "password": PASSWORD, **extra}
        return self.client.post(reverse("login"), data)

    def test_login_lands_on_saved_games(self):
        self.assertRedirects(self.login(), reverse("games:saved_games"))

    def test_login_honors_a_safe_next(self):
        self.assertRedirects(self.login(next=reverse("games:search")), reverse("games:search"))

    def test_login_ignores_an_off_site_next(self):
        for unsafe in ("https://evil.example/", "//evil.example/games/"):
            with self.subTest(next=unsafe):
                self.client.logout()
                self.assertRedirects(self.login(next=unsafe), reverse("games:saved_games"))

    def test_wrong_password_stays_on_login_with_an_error(self):
        response = self.client.post(reverse("login"), {"username": "player", "password": "wrong"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "alert-danger")
        self.assertNotIn("_auth_user_id", self.client.session)


class ProtectedPageTests(TestCase):
    def test_signed_out_visitors_are_sent_to_login_with_next(self):
        for name in ("games:saved_games", "games:search"):
            with self.subTest(page=name):
                url = reverse(name)
                response = self.client.get(url)
                self.assertRedirects(response, f"{reverse('login')}?next={url}")

    def test_signing_in_from_the_redirect_returns_to_the_requested_page(self):
        User.objects.create_user("player", password=PASSWORD)
        url = reverse("games:saved_games")
        login_page = self.client.get(url, follow=True)
        self.assertContains(login_page, f'name="next" value="{url}"')

        response = self.client.post(
            f"{reverse('login')}?next={url}",
            {"username": "player", "password": PASSWORD, "next": url},
        )
        self.assertRedirects(response, url)

    def test_saved_games_shows_the_empty_state_when_signed_in(self):
        self.client.force_login(User.objects.create_user("player", password=PASSWORD))
        response = self.client.get(reverse("games:saved_games"))
        self.assertContains(response, "You haven't saved any games yet.")


class LogoutTests(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_user("player", password=PASSWORD))

    def test_logout_by_get_is_rejected_and_keeps_the_session(self):
        response = self.client.get(reverse("logout"))
        self.assertEqual(response.status_code, 405)
        self.assertIn("_auth_user_id", self.client.session)

    def test_logout_by_post_signs_out_and_goes_to_login(self):
        response = self.client.post(reverse("logout"))
        self.assertRedirects(response, reverse("login"))
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertRedirects(
            self.client.get(reverse("games:saved_games")),
            f"{reverse('login')}?next={reverse('games:saved_games')}",
        )
