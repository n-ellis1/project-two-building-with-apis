"""The shared tracking validation function (stories 41, 42, 43, 45, 80)."""

from datetime import date

from django.core.exceptions import ValidationError
from django.test import TestCase

from games.validation import validate_tracking

from .factories import make_game


class PlatformPlayedValidationTests(TestCase):
    def test_platform_must_be_blank_listed_or_the_unchanged_stored_value(self):
        # The stored "PlayStation" is stale: the game no longer lists it.
        game = make_game("Resident Evil 2", platforms=["PlayStation 4", "PC (Microsoft Windows)"])
        stored = "PlayStation"

        for platform in ("", "PlayStation 4", stored):
            with self.subTest(accepted=platform):
                validate_tracking(
                    game, {"platform_played": platform}, stored_platform_played=stored
                )

        with self.assertRaises(ValidationError) as caught:
            validate_tracking(
                game, {"platform_played": "Nintendo 64"}, stored_platform_played=stored
            )
        self.assertEqual(
            caught.exception.message_dict,
            {"platform_played": ["Choose one of this game's platforms, or leave it blank."]},
        )


class DateValidationTests(TestCase):
    def test_finish_date_may_not_be_before_the_start_date(self):
        game = make_game("Celeste")
        march_1, march_9 = date(2026, 3, 1), date(2026, 3, 9)

        for start, finish in (
            (None, None),
            (march_1, None),
            (None, march_9),
            (march_1, march_1),
            (march_1, march_9),
        ):
            with self.subTest(accepted=(start, finish)):
                validate_tracking(game, {"start_date": start, "finish_date": finish})

        with self.assertRaises(ValidationError) as caught:
            validate_tracking(game, {"start_date": march_9, "finish_date": march_1})
        self.assertEqual(
            caught.exception.message_dict,
            {"finish_date": ["Finish date can't be before the start date."]},
        )
