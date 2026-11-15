"""Covers: one shared URL builder and the rendered <img> contract (stories 69-73)."""

from html.parser import HTMLParser

from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.template import Context, Template
from django.templatetags.static import static
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from games.covers import PLACEHOLDER_STATIC_PATH, cover_url
from games.models import Game

User = get_user_model()

FALLBACK_SCRIPT_PATH = "games/js/cover-fallback.js"


class CoverUrlTests(SimpleTestCase):
    def test_builds_igdb_image_urls_for_each_size_and_nothing_for_a_missing_id(self):
        base = "https://images.igdb.com/igdb/image/upload"
        cases = [
            ("co1rs4", "small", f"{base}/t_cover_small/co1rs4.jpg"),
            ("co1rs4", "small_2x", f"{base}/t_cover_small_2x/co1rs4.jpg"),
            ("co1rs4", "large", f"{base}/t_cover_big/co1rs4.jpg"),
            ("", "small", None),
            (None, "large", None),
        ]
        for image_id, size, expected in cases:
            with self.subTest(image_id=image_id, size=size):
                self.assertEqual(cover_url(image_id, size), expected)


class ImgCollector(HTMLParser):
    """Collects the attributes of every <img> and notes any <script> tag."""

    def __init__(self):
        super().__init__()
        self.imgs = []
        self.has_script = False

    def handle_starttag(self, tag, attrs):
        if tag == "img":
            self.imgs.append(dict(attrs))
        elif tag == "script":
            self.has_script = True


def render_cover(test, game, size):
    """Render `{% cover_img %}` and return (its single <img> attrs, parser, html)."""
    html = Template("{% load game_covers %}{% cover_img game size %}").render(
        Context({"game": game, "size": size})
    )
    parser = ImgCollector()
    parser.feed(html)
    test.assertEqual(len(parser.imgs), 1, html)
    return parser.imgs[0], parser, html


class CoverImgTagTests(SimpleTestCase):
    def render(self, game, size):
        return render_cover(self, game, size)

    def test_small_cover_has_fixed_size_lazy_loading_title_alt_and_2x_srcset(self):
        game = Game(name="The Witcher 3: Wild Hunt", cover_image_id="co1wyy")

        img, _, _ = self.render(game, "small")

        self.assertEqual(img["src"], cover_url("co1wyy", "small"))
        self.assertEqual(img["srcset"], f"{cover_url('co1wyy', 'small_2x')} 2x")
        self.assertEqual(img["width"], "90")
        self.assertEqual(img["height"], "128")
        self.assertEqual(img["loading"], "lazy")
        self.assertEqual(img["alt"], "The Witcher 3: Wild Hunt")

    def test_no_cover_id_renders_the_local_placeholder_without_srcset_or_js(self):
        game = Game(name="Coverless Game", cover_image_id="")

        img, parser, html = self.render(game, "small")

        self.assertEqual(img["src"], static("games/img/cover-placeholder.svg"))
        self.assertNotIn("srcset", img)
        self.assertEqual(img["width"], "90")
        self.assertEqual(img["height"], "128")
        self.assertEqual(img["loading"], "lazy")
        self.assertEqual(img["alt"], "Coverless Game")
        # The placeholder is in the HTML itself: no inline handler or script needed.
        self.assertNotIn("onerror", img)
        self.assertFalse(parser.has_script, html)
        self.assertNotIn("igdb.com", html)
        # Not marked for the fallback script, so a failed placeholder is left alone.
        self.assertNotIn("data-cover-placeholder", img)


class CoverFallbackContractTests(TestCase):
    """What the fallback script relies on. Its runtime behavior (switching a failed
    remote cover, ignoring a failed placeholder or an unrelated image) is checked in
    the browser with images.igdb.com blocked, because the stack has no JS engine.
    """

    def test_remote_cover_is_marked_with_the_placeholder_and_no_inline_handler(self):
        game = Game(name="The Witcher 3: Wild Hunt", cover_image_id="co1wyy")

        img, parser, html = render_cover(self, game, "small")

        self.assertEqual(img["data-cover-placeholder"], static(PLACEHOLDER_STATIC_PATH))
        self.assertNotIn("onerror", img)
        self.assertFalse(parser.has_script, html)

    def test_fallback_script_is_a_local_static_file(self):
        self.assertIsNotNone(finders.find(FALLBACK_SCRIPT_PATH))

    def test_every_page_loads_the_fallback_script_deferred_from_local_static(self):
        script = f'<script src="{static(FALLBACK_SCRIPT_PATH)}" defer></script>'

        self.assertContains(self.client.get(reverse("login")), script, html=True)

        self.client.force_login(User.objects.create_user("player", password="x"))
        self.assertContains(self.client.get(reverse("games:saved_games")), script, html=True)
