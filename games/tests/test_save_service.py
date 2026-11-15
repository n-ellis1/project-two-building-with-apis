"""The save service, with the IGDB client mocked at its module boundary.

No test here contacts Twitch or IGDB.
"""

import threading
from decimal import Decimal
from unittest import mock

from django.db import DatabaseError, IntegrityError, OperationalError, connection
from django.test import SimpleTestCase, TestCase, TransactionTestCase

from games import igdb
from games.models import (
    ELIGIBLE_GAME_CATEGORIES,
    Entry,
    Game,
    GameCategory,
    Genre,
    Platform,
    Theme,
    is_eligible,
)
from games.saving import GENERIC_SAVE_MESSAGE, SaveFailed, save_game
from games.tests.factories import make_entry, make_game, make_user


def row_counts() -> dict[str, int]:
    """Every table a save can write to, including the Game link tables."""
    return {
        "Game": Game.objects.count(),
        "Platform": Platform.objects.count(),
        "Genre": Genre.objects.count(),
        "Theme": Theme.objects.count(),
        "Entry": Entry.objects.count(),
        "Game-Platform links": Game.platforms.through.objects.count(),
        "Game-Genre links": Game.genres.through.objects.count(),
        "Game-Theme links": Game.themes.through.objects.count(),
    }


class OutageSaveTests(TestCase):
    """TDD cycle 1: saving during an IGDB outage."""

    def test_during_an_outage_a_stored_game_saves_and_a_new_game_saves_nothing(self):
        user_a, user_b = make_user("user_a"), make_user("user_b")
        stored = make_game(
            "Hollow Knight",
            igdb_id=14593,
            platforms=["PC (Microsoft Windows)"],
            genres=["Platform"],
            themes=[(1, "Action")],
        )
        make_entry(user_a, stored)
        new_igdb_id = 26758  # not in SQLite

        outage = igdb.IgdbError("igdb_unreachable")
        with mock.patch("games.igdb.fetch_game", side_effect=outage) as fetch:
            # B saves the game A already stored: works with no IGDB call.
            result = save_game(user_b, stored.igdb_id)

            entry = Entry.objects.filter(owner=user_b, game=stored).first()
            self.assertIsNotNone(entry, "B should now have an entry for the stored game")
            self.assertEqual(entry.status, Entry.Status.WANT_TO_PLAY)
            self.assertFalse(entry.favorite)
            self.assertEqual(result.entry, entry)
            self.assertTrue(result.created)
            fetch.assert_not_called()

            # B saves a game nobody stored: the outage error, and nothing written.
            before = row_counts()
            with self.assertRaises(igdb.IgdbError) as raised:
                save_game(user_b, new_igdb_id)

        self.assertEqual(raised.exception.code, "igdb_unreachable")
        fetch.assert_called_once_with(new_igdb_id)
        self.assertEqual(row_counts(), before)
        self.assertFalse(Game.objects.filter(igdb_id=new_igdb_id).exists())


# (label, game_type, version_parent) for releases the allowlist excludes.
EXCLUDED_CASES = [
    ("Main Game with a version parent (DS3 Day One Edition)", GameCategory.MAIN_GAME, 11133),
    ("Bundle", GameCategory.BUNDLE, None),
    ("Mod", GameCategory.MOD, None),
    ("Pack / Addon", GameCategory.PACK, None),
    ("Update", GameCategory.UPDATE, None),
    ("unknown future type", 15, None),
]


def fetched(igdb_id, game_type, version_parent=None, name="Fetched Game"):
    """A fetched record with one platform, genre and theme, so a wrongly allowed
    save would add rows to every table."""
    return igdb.IgdbGameDetails(
        igdb_id=igdb_id,
        name=name,
        game_category=game_type,
        version_parent=version_parent,
        platforms=(igdb.IgdbNamed(900_000 + igdb_id, f"Platform {igdb_id}"),),
        genres=(igdb.IgdbNamed(900_000 + igdb_id, f"Genre {igdb_id}"),),
        themes=(igdb.IgdbNamed(900_000 + igdb_id, f"Theme {igdb_id}"),),
    )


class IsEligibleTests(SimpleTestCase):
    """The one shared eligibility rule, on its own."""

    def test_only_an_allowlisted_type_with_no_version_parent_is_eligible(self):
        for game_type in range(-1, 17):
            with self.subTest(game_type=game_type):
                self.assertEqual(
                    is_eligible(game_type, None), game_type in ELIGIBLE_GAME_CATEGORIES
                )
                self.assertFalse(is_eligible(game_type, 11133))
        self.assertTrue(is_eligible(GameCategory.MAIN_GAME, None))  # 0 is valid, not "missing"
        self.assertFalse(is_eligible(None, None))  # missing game_type
        self.assertFalse(is_eligible(True, None))  # a JSON true is not type 1


class EligibilityTests(TestCase):
    """TDD cycle 2: the eligibility rule (no version parent, Game Category on the
    allowlist) on both save paths."""

    def test_excluded_releases_are_refused_on_both_paths_and_eligible_ones_save(self):
        user = make_user("saver")

        for number, (label, game_type, version_parent) in enumerate(EXCLUDED_CASES):
            with self.subTest(path="stored", case=label):
                # Stored by someone else, so it is a real shared Game.
                stored = make_game(
                    f"Stored {label}",
                    igdb_id=500 + number,
                    game_category=game_type,
                    version_parent=version_parent,
                    platforms=["PC (Microsoft Windows)"],
                )
                make_entry(make_user(f"other_{number}"), stored)
                before = row_counts()
                with mock.patch("games.igdb.fetch_game") as fetch:
                    with self.assertRaises(igdb.IgdbError) as raised:
                        save_game(user, stored.igdb_id)
                self.assertEqual(raised.exception.code, "game_category_excluded")
                fetch.assert_not_called()
                self.assertEqual(row_counts(), before)

            with self.subTest(path="fetched", case=label):
                igdb_id = 600 + number
                record = fetched(igdb_id, game_type, version_parent)
                before = row_counts()
                with mock.patch("games.igdb.fetch_game", return_value=record) as fetch:
                    with self.assertRaises(igdb.IgdbError) as raised:
                        save_game(user, igdb_id)
                self.assertEqual(raised.exception.code, "game_category_excluded")
                fetch.assert_called_once_with(igdb_id)
                self.assertEqual(row_counts(), before)
                self.assertFalse(Game.objects.filter(igdb_id=igdb_id).exists())

        # A record IGDB sent without a game_type. Only the fetched path can have one:
        # the stored Game Category is non-nullable.
        with self.subTest(path="fetched", case="missing game_type"):
            record = fetched(699, None)
            before = row_counts()
            with mock.patch("games.igdb.fetch_game", return_value=record):
                with self.assertRaises(igdb.IgdbError) as raised:
                    save_game(user, 699)
            self.assertEqual(raised.exception.code, "game_category_excluded")
            self.assertEqual(row_counts(), before)

        # Regression: every allowlisted Game Category still saves on both paths.
        for game_type in sorted(ELIGIBLE_GAME_CATEGORIES):
            with self.subTest(path="stored", eligible=game_type):
                stored = make_game(igdb_id=700 + game_type, game_category=game_type)
                with mock.patch("games.igdb.fetch_game") as fetch:
                    result = save_game(user, stored.igdb_id)
                fetch.assert_not_called()
                self.assertTrue(result.created)
                self.assertEqual(result.entry.game, stored)

            with self.subTest(path="fetched", eligible=game_type):
                igdb_id = 800 + game_type
                record = fetched(igdb_id, game_type, name=f"New {game_type}")
                with mock.patch("games.igdb.fetch_game", return_value=record):
                    result = save_game(user, igdb_id)
                self.assertTrue(result.created)
                game = Game.objects.get(igdb_id=igdb_id)
                self.assertEqual(result.entry.game, game)
                self.assertEqual(result.entry.owner, user)
                self.assertEqual(game.game_category, game_type)
                self.assertIsNone(game.version_parent)
                self.assertEqual([p.igdb_id for p in game.platforms.all()], [900_000 + igdb_id])
                self.assertEqual([g.igdb_id for g in game.genres.all()], [900_000 + igdb_id])
                self.assertEqual([t.igdb_id for t in game.themes.all()], [900_000 + igdb_id])


TRACKING = {
    "status": Entry.Status.PLAYING,
    "favorite": True,
    "rating": 8,
    "notes": "Stuck on the Mantis Lords.",
    "platform_played": "PC (Microsoft Windows)",
    "hours_played": Decimal("12.5"),
}


def tracking_of(entry) -> dict:
    entry.refresh_from_db()
    return {name: getattr(entry, name) for name in TRACKING}


class DuplicateAndRollbackTests(TestCase):
    """TDD cycle 3: repeat saves, integrity errors during simultaneous saves, and
    rollback when the Entry write fails after new metadata was written."""

    def setUp(self):
        self.user_a, self.user_b = make_user("user_a"), make_user("user_b")
        self.game = make_game("Hollow Knight", igdb_id=14593, platforms=["PC (Microsoft Windows)"])
        self.real_create = Entry.objects.create

    def save(self, user, igdb_id):
        """save_game, failing (not erroring) if a raw database error escapes it."""
        try:
            return save_game(user, igdb_id)
        except DatabaseError as error:
            self.fail(f"save_game let a raw {type(error).__name__} escape")

    def assert_save_failed(self, user, igdb_id) -> SaveFailed:
        try:
            save_game(user, igdb_id)
        except SaveFailed as error:
            self.assertEqual(error.message, GENERIC_SAVE_MESSAGE)
            self.assertEqual(str(error), GENERIC_SAVE_MESSAGE)
            return error
        except DatabaseError as error:
            self.fail(f"save_game let a raw {type(error).__name__} escape")
        self.fail("save_game did not raise SaveFailed")

    def test_a_repeat_save_returns_the_existing_entry_unchanged(self):
        existing = make_entry(self.user_b, self.game, **TRACKING)

        with mock.patch("games.igdb.fetch_game") as fetch:
            result = self.save(self.user_b, self.game.igdb_id)

        self.assertFalse(result.created)
        self.assertEqual(result.entry, existing)
        self.assertEqual(Entry.objects.filter(owner=self.user_b, game=self.game).count(), 1)
        self.assertEqual(tracking_of(existing), TRACKING)
        fetch.assert_not_called()

    def test_an_integrity_error_with_only_another_users_entry_is_not_a_duplicate(self):
        theirs = make_entry(self.user_a, self.game, **TRACKING)

        with mock.patch.object(
            Entry.objects, "create", side_effect=IntegrityError("simulated: not a duplicate")
        ):
            error = self.assert_save_failed(self.user_b, self.game.igdb_id)

        self.assertNotIn("simulated", str(error))
        self.assertFalse(Entry.objects.filter(owner=self.user_b).exists())
        self.assertEqual(tracking_of(theirs), TRACKING)
        self.assertEqual(Entry.objects.filter(game=self.game).count(), 1)

    def test_an_entry_write_failure_rolls_back_the_new_game_and_its_links(self):
        new_id = 26758
        record = fetched(new_id, GameCategory.MAIN_GAME, name="Hollow Knight: Silksong")
        before = row_counts()
        seen_inside = {}

        def entry_write_fails(**fields):
            # By now the new Game and its links must already be written.
            game = Game.objects.get(igdb_id=new_id)
            seen_inside["game"] = True
            seen_inside["links"] = (
                game.platforms.count(),
                game.genres.count(),
                game.themes.count(),
            )
            raise OperationalError("simulated: database is locked")

        with (
            mock.patch("games.igdb.fetch_game", return_value=record),
            mock.patch.object(Entry.objects, "create", side_effect=entry_write_fails),
        ):
            error = self.assert_save_failed(self.user_b, new_id)

        self.assertEqual(seen_inside, {"game": True, "links": (1, 1, 1)})
        self.assertNotIn("simulated", str(error))
        self.assertEqual(row_counts(), before)
        self.assertFalse(Game.objects.filter(igdb_id=new_id).exists())


def committed_elsewhere(write):
    """Run `write` on another thread, which has its own database connection, so it
    commits for real (like a second browser tab's request) and our rollback can't undo
    it. Returns what `write` returned."""
    box = {}

    def run():
        try:
            box["value"] = write()
        except BaseException as error:  # re-raised on the test thread
            box["error"] = error
        finally:
            connection.close()

    thread = threading.Thread(target=run)
    thread.start()
    thread.join()
    if "error" in box:
        raise box["error"]
    return box.get("value")


class SimultaneousSaveTests(TransactionTestCase):
    """Saves that race a second request. A TransactionTestCase, so the other request's
    write is really committed on its own connection."""

    def setUp(self):
        self.user_a, self.user_b = make_user("user_a"), make_user("user_b")
        self.game = make_game("Hollow Knight", igdb_id=14593, platforms=["PC (Microsoft Windows)"])
        self.real_create = Entry.objects.create

    def save(self, user, igdb_id):
        """save_game, failing (not erroring) if a raw database error escapes it."""
        try:
            return save_game(user, igdb_id)
        except DatabaseError as error:
            self.fail(f"save_game let a raw {type(error).__name__} escape")

    def test_an_integrity_error_with_my_entry_confirmed_is_a_duplicate(self):
        """TDD cycle 3. The other tab's save commits between our check and our insert,
        so our insert hits the (owner, game) constraint for real."""
        winner = {}

        def other_tab_wins_then_insert(**fields):
            winner["entry"] = committed_elsewhere(
                lambda: self.real_create(owner=self.user_b, game=self.game, **TRACKING)
            )
            return self.real_create(**fields)  # raises a genuine IntegrityError

        with mock.patch.object(Entry.objects, "create", side_effect=other_tab_wins_then_insert):
            result = self.save(self.user_b, self.game.igdb_id)

        self.assertFalse(result.created)
        self.assertEqual(result.entry, winner["entry"])
        self.assertEqual(Entry.objects.filter(owner=self.user_b, game=self.game).count(), 1)
        self.assertEqual(tracking_of(winner["entry"]), TRACKING)

    def test_any_other_database_error_is_generic_even_if_my_entry_now_exists(self):
        """Only an IntegrityError can be a duplicate. Here my other tab's entry is
        committed, but our own write fails for an unrelated reason."""

        def other_tab_commits_then_db_fails(**fields):
            committed_elsewhere(lambda: self.real_create(owner=self.user_b, game=self.game))
            raise OperationalError("simulated: disk I/O error")

        with mock.patch.object(
            Entry.objects, "create", side_effect=other_tab_commits_then_db_fails
        ):
            with self.assertRaises(SaveFailed) as raised:
                save_game(self.user_b, self.game.igdb_id)

        self.assertEqual(str(raised.exception), GENERIC_SAVE_MESSAGE)
        self.assertIsNone(raised.exception.__cause__)

    def fetch_while_another_request_stores(self, new_id, **stored_fields):
        """A fake fetch_game: while our IGDB request is in flight, another user's
        request stores the same new Game (committed), so our Game insert collides."""
        record = fetched(new_id, GameCategory.MAIN_GAME, name="Hollow Knight: Silksong")

        def fetch(igdb_id):
            committed_elsewhere(
                lambda: make_game("Silksong (theirs)", igdb_id=new_id, **stored_fields)
            )
            return record

        return mock.patch("games.igdb.fetch_game", side_effect=fetch)

    def test_a_colliding_new_game_insert_reuses_the_stored_game_once(self):
        new_id = 26758
        with self.fetch_while_another_request_stores(new_id) as fetch:
            result = self.save(self.user_b, new_id)

        fetch.assert_called_once_with(new_id)  # no second IGDB call
        self.assertTrue(result.created)
        stored = Game.objects.get(igdb_id=new_id)
        self.assertEqual(stored.name, "Silksong (theirs)")  # the other request's row
        self.assertEqual(result.entry.game, stored)
        self.assertEqual(result.entry.owner, self.user_b)
        self.assertEqual(Entry.objects.filter(owner=self.user_b, game=stored).count(), 1)
        # Our fetched links were rolled back with our failed insert.
        self.assertFalse(Platform.objects.filter(igdb_id=900_000 + new_id).exists())

    def test_a_colliding_new_game_is_rechecked_for_eligibility_on_the_stored_row(self):
        new_id = 26759
        with self.fetch_while_another_request_stores(new_id, version_parent=11133) as fetch:
            with self.assertRaises(igdb.IgdbError) as raised:
                self.save(self.user_b, new_id)

        self.assertEqual(raised.exception.code, "game_category_excluded")
        fetch.assert_called_once_with(new_id)
        self.assertFalse(Entry.objects.filter(owner=self.user_b).exists())
