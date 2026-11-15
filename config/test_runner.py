"""Test runner that keeps the whole suite offline.

`manage.py test` loads the developer's real `.env`, so without this a test that
reaches the IGDB client unmocked (for example any blank Search IGDB page, which asks
for the "Popular on IGDB" row) would contact Twitch and IGDB for real.

- IGDB credentials are blanked for every test, so an unmocked client raises
  `igdb_misconfigured` before any request (pages then behave as "not set up").
- `requests.post` is replaced for the whole run, so a test that sets fake credentials
  but forgets to mock HTTP fails loudly instead of going to the network.

Tests that need the client still use `override_settings` with fake credentials and
patch `games.igdb.requests.post` (or the client functions); both nest over this.
"""

from unittest import mock

from django.test.runner import DiscoverRunner
from django.test.utils import override_settings


def _refuse_network(url, *args, **kwargs):
    raise AssertionError(
        "A test tried to make a real HTTP request. Mock games.igdb.requests.post "
        "(client tests) or games.igdb.search_games / fetch_game / popular_games (views)."
    )


class OfflineTestRunner(DiscoverRunner):
    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        self._no_credentials = override_settings(IGDB_CLIENT_ID="", IGDB_CLIENT_SECRET="")
        self._no_credentials.enable()
        self._no_network = mock.patch("requests.post", side_effect=_refuse_network)
        self._no_network.start()

    def teardown_test_environment(self, **kwargs):
        self._no_network.stop()
        self._no_credentials.disable()
        super().teardown_test_environment(**kwargs)
