"""Small helpers for building test data. Nothing here contacts IGDB."""

from itertools import count

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

from games.models import Entry, Game, Genre, Platform, Theme

User = get_user_model()
_ids = count(1_000_000)


def make_user(username: str, password: str = "test-pass-not-real") -> User:
    return User.objects.create_user(username, password=password)


def make_game(name: str = "Test Game", platforms=(), genres=(), themes=(), **fields) -> Game:
    """A Game linked to platforms, genres and themes given by name.

    A theme may also be an `(igdb_id, name)` pair, for tests that need a real
    IGDB theme ID such as `(19, "Horror")`.
    """
    igdb_id = fields.pop("igdb_id", next(_ids))
    game = Game.objects.create(igdb_id=igdb_id, name=name, last_fetched_at=timezone.now(), **fields)
    for model, related, names in (
        (Platform, game.platforms, platforms),
        (Genre, game.genres, genres),
        (Theme, game.themes, themes),
    ):
        for item in names:
            item_id, item_name = item if isinstance(item, tuple) else (None, item)
            obj, _ = model.objects.get_or_create(
                name=item_name, defaults={"igdb_id": item_id or next(_ids)}
            )
            related.add(obj)
    return game


def make_entry(owner, game=None, **fields) -> Entry:
    return Entry.objects.create(owner=owner, game=game or make_game(), **fields)


def csrf_client(user, token_page: str) -> tuple[Client, str]:
    """A signed-in client that enforces CSRF, plus a valid token for it.

    `token_page` is any page the user can open that renders `{% csrf_token %}`,
    so the CSRF cookie gets set.
    """
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)
    response = client.get(token_page)
    assert response.status_code == 200, response.status_code
    return client, client.cookies[settings.CSRF_COOKIE_NAME].value
