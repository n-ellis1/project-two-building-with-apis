"""Seed two demo users with saved entries from stored data. Never contacts IGDB.

    uv run python manage.py seed_demo

Both demo accounts use the password in DEMO_PASSWORD (from .env or the shell).
Safe to rerun: existing demo accounts keep their passwords, existing Games and
entries are never changed, and only missing rows are added. If a demo username
belongs to an account this command didn't create, it stops before changing anything.
"""

import json
import os
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.dateparse import parse_date, parse_datetime

from games.models import DemoAccount, Entry, Game, Genre, Platform, Theme

PASSWORD_VARIABLE = "DEMO_PASSWORD"
FIXTURE = Path(__file__).resolve().parents[2] / "demo_data" / "seed.json"
ENTRY_FIELDS = (
    "status",
    "favorite",
    "rating",
    "notes",
    "platform_played",
    "hours_played",
)
DATE_FIELDS = ("start_date", "finish_date")


class Command(BaseCommand):
    help = "Create two demo users with saved entries from stored data (no IGDB calls)."

    def handle(self, *args, **options):
        password = os.environ.get(PASSWORD_VARIABLE, "").strip()
        if not password:
            raise CommandError(
                f"{PASSWORD_VARIABLE} is not set. Add {PASSWORD_VARIABLE}=<a password> to .env "
                "(see .env.example) and run the command again. Nothing was created."
            )

        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        usernames = list(data["users"])
        self.check_demo_accounts(usernames)

        with transaction.atomic():
            users = self.seed_users(usernames, password)
            games = self.seed_games(data["games"], parse_datetime(data["fetched_at"]))
            self.seed_entries(data["users"], users, games)

    def check_demo_accounts(self, usernames):
        """Stop before any change if a demo username belongs to someone else."""
        User = get_user_model()
        foreign = [
            user.get_username()
            for user in User.objects.filter(username__in=usernames)
            if not DemoAccount.objects.filter(user=user).exists()
        ]
        if foreign:
            raise CommandError(
                f"The username(s) {', '.join(sorted(foreign))} already belong to account(s) "
                "this command didn't create, so it stopped without changing anything. "
                "Rename or remove those accounts, then run the command again."
            )

    def seed_users(self, usernames, password):
        User = get_user_model()
        users, created = {}, 0
        for username in usernames:
            user = User.objects.filter(username=username).first()
            if user is None:
                user = User.objects.create_user(username, password=password)
                DemoAccount.objects.create(user=user)
                created += 1
            users[username] = user
        self.report("Demo users", created, len(usernames) - created, "password unchanged")
        return users

    def seed_games(self, records, fetched_at):
        games, created = {}, 0
        for record in records:
            game = Game.objects.filter(igdb_id=record["igdb_id"]).first()
            if game is None:
                game = Game.objects.create(
                    igdb_id=record["igdb_id"],
                    name=record["name"],
                    slug=record["slug"],
                    summary=record["summary"],
                    first_release_date=parse_date(record["first_release_date"] or ""),
                    game_category=record["game_category"],
                    version_parent=record["version_parent"],
                    cover_image_id=record["cover_image_id"],
                    igdb_url=record["igdb_url"],
                    last_fetched_at=fetched_at,
                )
                game.platforms.set(self.named_items(Platform, record["platforms"]))
                game.genres.set(self.named_items(Genre, record["genres"]))
                game.themes.set(self.named_items(Theme, record["themes"]))
                created += 1
            games[game.igdb_id] = game
        self.report("Games", created, len(records) - created, "left as stored")
        return games

    @staticmethod
    def named_items(model, items):
        return [
            model.objects.get_or_create(igdb_id=item["igdb_id"], defaults={"name": item["name"]})[0]
            for item in items
        ]

    def seed_entries(self, entries_by_user, users, games):
        created = present = 0
        for username, entries in entries_by_user.items():
            for item in entries:
                defaults = {name: item[name] for name in ENTRY_FIELDS if name in item}
                defaults.update(
                    {name: parse_date(item[name]) for name in DATE_FIELDS if name in item}
                )
                defaults["created_at"] = parse_datetime(item["added"])
                _, was_created = Entry.objects.get_or_create(
                    owner=users[username], game=games[item["igdb_id"]], defaults=defaults
                )
                created += was_created
                present += not was_created
        self.report("Entries", created, present, "left unchanged")

    def report(self, label, created, present, note):
        self.stdout.write(f"{label}: {created} created, {present} already present ({note}).")
