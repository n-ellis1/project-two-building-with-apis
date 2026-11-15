"""Small helpers for building test data. Nothing here contacts IGDB."""

from itertools import count

from django.contrib.auth import get_user_model
from django.utils import timezone

from games.models import Entry, Game, Platform

User = get_user_model()
_ids = count(1_000_000)


def make_user(username: str, password: str = "test-pass-not-real") -> User:
    return User.objects.create_user(username, password=password)


def make_game(name: str = "Test Game", platforms=(), **fields) -> Game:
    igdb_id = fields.pop("igdb_id", next(_ids))
    game = Game.objects.create(igdb_id=igdb_id, name=name, last_fetched_at=timezone.now(), **fields)
    for platform_name in platforms:
        platform, _ = Platform.objects.get_or_create(
            name=platform_name, defaults={"igdb_id": next(_ids)}
        )
        game.platforms.add(platform)
    return game


def make_entry(owner, game=None, **fields) -> Entry:
    return Entry.objects.create(owner=owner, game=game or make_game(), **fields)
