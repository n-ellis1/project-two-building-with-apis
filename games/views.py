from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.cache import patch_vary_headers
from django.views.decorators.http import require_http_methods, require_POST

from . import igdb
from .forms import EntryForm, SignupForm
from .models import Entry, Game, is_eligible
from .queries import (
    MAX_SEARCH_LENGTH,
    PAGE_SIZE,
    SORT_LABELS,
    EntryQuery,
    get_owned_entry_or_404,
    owned_entries,
    parse_entry_query,
    parse_page,
    resolve_saved_search,
    roman_numeral_variant,
    saved_entries,
    saved_games_url,
    user_platforms_played,
    user_themes,
)
from .saving import RefreshFailed, SaveFailed, refresh_game, save_game


def home(request):
    if request.user.is_authenticated:
        return redirect("games:saved_games")
    return redirect("login")


def signup(request):
    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("games:saved_games")
    else:
        form = SignupForm()
    return render(request, "registration/signup.html", {"form": form})


def saved_games_context(user, query: EntryQuery, page_number: int) -> dict:
    """Everything the My Saved Games region renders, built from one parsed query.

    The controls (search box, Status, Platform Played, Favorite, Theme, sort), the
    results, the pager, Clear filters and the detail links all come from `query`
    and the resolved page, so they always agree with each other and with the URL.

    The search term may resolve to its Roman-numeral form ("Dark Souls 3" finds
    "Dark Souls III") when the typed term matches nothing under the active filters.
    That is decided on the whole filtered list, before paging, so every page of the
    same URL runs the same search. The URL, the search box and every link keep the
    typed term; only the results and the notice use the matched one.
    """
    effective = resolve_saved_search(user, query)
    paginator = Paginator(saved_entries(user, effective), PAGE_SIZE)
    page_obj = paginator.get_page(page_number)
    number = page_obj.number
    return {
        "page_obj": page_obj,
        "query": query,
        "matched_q": effective.q if effective.q != query.q else "",
        "has_entries": owned_entries(user).exists(),
        "status_choices": Entry.Status.choices,
        "platform_choices": user_platforms_played(user),
        "theme_choices": user_themes(user),
        "sort_choices": SORT_LABELS.items(),
        "sort_label": SORT_LABELS[query.sort],
        "clear_filters_url": saved_games_url(query.without_filters()),
        "previous_url": saved_games_url(query, number - 1) if page_obj.has_previous() else "",
        "next_url": saved_games_url(query, number + 1) if page_obj.has_next() else "",
        # Detail links carry the list state, so the detail page can return to it.
        "detail_querystring": query.querystring(number),
    }


def is_htmx_swap(request) -> bool:
    """An ordinary HTMX request, which swaps in just the region.

    A history restore that missed HTMX's cache also sends `HX-Request`, but it
    replaces the whole page, so it must get the full page.
    """
    return (
        request.headers.get("HX-Request") == "true"
        and request.headers.get("HX-History-Restore-Request") != "true"
    )


@login_required
def saved_games(request):
    """My Saved Games, read only from SQLite (never contacts IGDB).

    One parsed query renders the controls and the results for all three kinds of
    request: a normal request and an HTMX history restore get the full page, and an
    ordinary HTMX request gets only the region, plus `HX-Push-Url` with the clean
    URL of what is actually shown (validated values only, no blanks, no default
    sort, the clamped page, no page 1).
    """
    query = parse_entry_query(request.user, request.GET)
    context = saved_games_context(request.user, query, parse_page(request.GET.get("page")))
    if is_htmx_swap(request):
        response = render(request, "games/_saved_games_region.html", context)
        response["HX-Push-Url"] = saved_games_url(query, context["page_obj"].number)
    else:
        response = render(request, "games/saved_games.html", context)
    # The same URL returns two different bodies, so caches must key on both headers.
    patch_vary_headers(response, ["HX-Request", "HX-History-Restore-Request"])
    return response


@login_required
def entry_detail(request, entry_id):
    """One of my entries, read only from SQLite. Anyone else's entry ID is a 404.

    The query string is the My Saved Games state the entry was opened from. It is
    parsed exactly like the list's (unknown values dropped, never echoed) and only
    ever becomes a link on our own route.
    """
    entry = get_owned_entry_or_404(request.user, entry_id)
    query = parse_entry_query(request.user, request.GET)
    page = parse_page(request.GET.get("page"))
    game = entry.game
    return render(
        request,
        "games/entry_detail.html",
        {
            "entry": entry,
            "game": game,
            "saved_games_return_url": saved_games_url(query, page),
            # The Refresh form posts the same validated list state, so the redirect
            # back here keeps the My Saved Games link.
            "list_querystring": query.querystring(page),
            # Kept, not changed: a refresh may have removed the platform (story 79).
            # Matched by exact name, like the shared validation.
            "platform_played_stale": bool(entry.platform_played)
            and not game.platforms.filter(name=entry.platform_played).exists(),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def entry_edit(request, entry_id):
    """Edit one of my entries' tracking fields. Anyone else's entry ID is a 404."""
    entry = get_owned_entry_or_404(request.user, entry_id)
    if request.method == "POST":
        form = EntryForm(request.POST, instance=entry)
        if form.is_valid():
            form.save()
            messages.success(request, f"Saved your changes to {entry.game.name}.")
            return redirect("games:entry_detail", entry_id=entry.pk)
    else:
        form = EntryForm(instance=entry)
    return render(
        request, "games/entry_edit.html", {"form": form, "entry": entry, "game": entry.game}
    )


@login_required
@require_http_methods(["GET", "POST"])
def entry_delete(request, entry_id):
    """GET only shows the confirmation; a POST (CSRF-checked by middleware) removes the entry.

    Both methods go through the owner-scoped lookup, so anyone else's entry is a 404.
    Deleting an entry never deletes the shared Game or other users' entries.
    """
    entry = get_owned_entry_or_404(request.user, entry_id)
    if request.method == "POST":
        game_name = entry.game.name
        entry.delete()
        messages.success(request, f"Removed {game_name} from My Games.")
        return redirect("games:saved_games")
    return render(request, "games/entry_confirm_delete.html", {"entry": entry, "game": entry.game})


REFRESH_THROTTLE_SECONDS = 10 * 60
REFRESH_THROTTLED_MESSAGE = (
    "A refresh was attempted for this game in the last 10 minutes. Try again later."
)


def refresh_attempt_key(igdb_id: int) -> str:
    """The shared cache key for a game's last refresh attempt (a game ID, no secrets)."""
    return f"igdb:refresh_attempt:{int(igdb_id)}"


@login_required
@require_POST
def entry_refresh(request, entry_id):
    """Refresh the shared Game behind one of my entries from IGDB (POST only, CSRF
    checked by middleware). Anyone else's entry ID is a 404, checked before the
    throttle, so it never calls IGDB or records an attempt.

    - **Throttled:** one attempt per game per 10 minutes across all users, recorded
      before the IGDB call and kept whatever happens, so failed attempts count too.
    - **Success:** the Game's details, links and last-fetched time, in one transaction.
    - **Failure:** nothing changes; the fixed message, with the My Saved Games link
      for upstream, configuration and unexpected failures.

    Always redirects back to my entry's detail page, carrying the My Saved Games
    state it was opened from (validated values only, never echoed raw).
    """
    entry = get_owned_entry_or_404(request.user, entry_id)
    game = entry.game
    query = parse_entry_query(request.user, request.GET)
    detail_url = reverse("games:entry_detail", args=[entry.pk]) + query.querystring(
        parse_page(request.GET.get("page"))
    )
    if not cache.add(refresh_attempt_key(game.igdb_id), True, REFRESH_THROTTLE_SECONDS):
        messages.info(request, REFRESH_THROTTLED_MESSAGE)
        return redirect(detail_url)
    try:
        refresh_game(game)
    except igdb.IgdbError as error:
        tags = "" if error.code in NO_LINK_CODES else SAVED_GAMES_LINK_TAG
        messages.error(request, error.message, extra_tags=tags)
    except RefreshFailed as error:
        messages.error(request, error.message, extra_tags=SAVED_GAMES_LINK_TAG)
    else:
        messages.success(request, f"Refreshed {game.name} from IGDB.")
    return redirect(detail_url)


@login_required
def search(request):
    """IGDB search (`q`, `page`). Login is checked first, so signed-out visitors never
    cause an IGDB call, and a blank search makes no call either.

    One IGDB request per page: 11 asked for, 10 shown, Next only if the 11th came
    back. Errors are shown apart from "No matches." and "No more results", with the
    search text kept in the box. HTMX pager requests get only the results region,
    with the clean URL in `HX-Push-Url`; normal requests and history restores get the
    full page (the same rules as My Saved Games).
    """
    q = clean_search_text(request.GET.get("q", ""))
    page = parse_page(request.GET.get("page"))
    context = {
        "q": q,
        "original_q": "",
        "page": page,
        "results": [],
        "error": None,
        "previous_url": "",
        "next_url": "",
    }
    if q:
        try:
            # The client asks for one extra result; it only tells us Next exists.
            results = igdb.search_games(q, page)
            # B2: "Dark Souls 3" finds nothing because IGDB titles spell it "III".
            # Only an empty page 1 (never an error) gets one Roman-numeral retry.
            fallback = roman_numeral_variant(q)
            if not results and page == 1 and fallback:
                fallback_results = igdb.search_games(fallback, 1)
                if fallback_results:
                    # From here on the matched term is the search, so the box, the
                    # pager and the pushed URL all use it.
                    context["original_q"], q, results = q, fallback, fallback_results
        except igdb.IgdbError as error:
            context["error"] = error.message
        else:
            shown = results[: igdb.SEARCH_PAGE_SIZE]
            context["results"] = with_saved_entries(request.user, shown)
            # An empty later page offers a page-1 link instead of Previous.
            if page > 1 and shown:
                context["previous_url"] = search_url(q, page - 1)
            if len(results) > igdb.SEARCH_PAGE_SIZE:
                context["next_url"] = search_url(q, page + 1)
    context["q"] = q
    context["first_page_url"] = search_url(q)

    htmx_swap = is_htmx_swap(request)
    # The row sits outside the swapped region, so only a full blank page needs it.
    context["popular"] = popular_row(request.user) if not q and not htmx_swap else []

    if htmx_swap:
        response = render(request, "games/_search_region.html", context)
        response["HX-Push-Url"] = search_url(q, page)
    else:
        response = render(request, "games/search.html", context)
    patch_vary_headers(response, ["HX-Request", "HX-History-Restore-Request"])
    return response


@login_required
def igdb_game(request, igdb_id):
    """Any IGDB game by IGDB ID, saved or not (login is checked before any IGDB call).

    - **Stored Game:** read from SQLite with no IGDB call, so it works during an outage.
    - **Not stored:** one `fetch_game` request. An unknown ID is a 404 with the fixed
      message; any other failure shows its fixed message with links to My Saved Games
      and Search IGDB.

    If I already saved it, the page links to **my** entry (owner-scoped lookup).
    Otherwise an eligible game gets a Save button on the existing `/search/save/`
    flow, and an ineligible one gets only the excluded message.
    """
    if igdb_id > MAX_IGDB_ID or igdb_id < 1:
        raise Http404
    context = {"game": None, "platforms": [], "error": None, "saved_entry_id": None}

    stored = Game.objects.filter(igdb_id=igdb_id).prefetch_related("platforms").first()
    if stored is not None:
        game = stored
        context["platforms"] = [platform.name for platform in stored.platforms.all()]
    else:
        try:
            game = igdb.fetch_game(igdb_id)
        except igdb.IgdbError as error:
            # A failed save from this page redirects here with the same fixed message
            # (and its My Saved Games link) already queued, so show it only once.
            pending = {str(message) for message in messages.get_messages(request)}
            context["error"] = None if error.message in pending else error.message
            # Upstream and configuration failures get the My Saved Games link.
            context["error_saved_games_link"] = error.code not in NO_LINK_CODES
            status = 404 if error.code == "igdb_game_not_found" else 200
            return render(request, "games/igdb_game.html", context, status=status)
        context["platforms"] = [platform.name for platform in game.platforms]

    context["game"] = game
    context["igdb_id"] = igdb_id
    context["saved_entry_id"] = (
        owned_entries(request.user)
        .filter(game__igdb_id=igdb_id)
        .values_list("pk", flat=True)
        .first()
    )
    context["eligible"] = is_eligible(game.game_category, game.version_parent)
    context["excluded_message"] = igdb.MESSAGES["game_category_excluded"]
    return render(request, "games/igdb_game.html", context)


def popular_row(user) -> list[dict]:
    """The "Popular on IGDB" row for the blank search page, or [] when the feed fails.

    The game list is shared and cached by the client. The Saved links are looked up
    here, for this user, on every request, so they never enter the cache. A failure
    just leaves the row out: no banner, and searching works as usual.
    """
    try:
        games = igdb.cached_popular_games()
    except igdb.IgdbError:
        return []
    return with_saved_entries(user, games)


def clean_search_text(value) -> str:
    """Search text with runs of whitespace collapsed, cut to the box's maximum length."""
    return " ".join(str(value).split())[:MAX_SEARCH_LENGTH]


# The largest ID a Game's IGDB ID column holds; anything bigger can't be a real game.
MAX_IGDB_ID = 2_147_483_647

# Messages tagged with this get a "Go to My Saved Games" link (upstream, configuration
# and unexpected failures), like the search page's own error alert.
SAVED_GAMES_LINK_TAG = "saved-games-link"
NO_LINK_CODES = {"igdb_game_not_found", "game_category_excluded"}
ALREADY_SAVED_MESSAGE = "Already in your games"
# The one recognised `return_to` value on /search/save/ (the IGDB game page's Save form).
RETURN_TO_IGDB_GAME = "igdb_game"


def parse_igdb_id(value) -> int | None:
    """A positive IGDB ID from a form value, or None. Digits only, no signs or spaces."""
    text = str(value or "")
    if not (text.isascii() and text.isdigit() and len(text) <= 10):
        return None
    number = int(text)
    return number if 0 < number <= MAX_IGDB_ID else None


@login_required
@require_POST
def search_save(request):
    """Save a search result to my games through the save service (POST only, CSRF
    checked by middleware). The owner is always the signed-in user.

    - **New save:** to the entry's edit page.
    - **Already mine:** to my existing entry, with "Already in your games".
    - **Failure:** back to the same search (`q`, `page`) with the fixed message. The
      message is stored in the session, so it still shows even if reloading the
      results fails too. A save from the IGDB game page (`return_to=igdb_game`) goes
      back to that page instead.

    The failure destination is only ever one of our own routes, built here with
    `reverse()`: `return_to` is matched as a name, never used as a URL, and the
    detail page URL is rebuilt from the validated IGDB ID. Any posted `next` or
    URL is ignored.
    """
    q = clean_search_text(request.POST.get("q", ""))
    page = parse_page(request.POST.get("page"))
    igdb_id = parse_igdb_id(request.POST.get("igdb_id"))
    if request.POST.get("return_to") == RETURN_TO_IGDB_GAME and igdb_id is not None:
        failure_url = reverse("games:igdb_game", args=[igdb_id])
    else:
        failure_url = search_url(q, page)

    if igdb_id is None:
        # Never sent to IGDB: it can't be a real game ID.
        messages.error(request, igdb.MESSAGES["igdb_game_not_found"])
        return redirect(failure_url)

    try:
        result = save_game(request.user, igdb_id)
    except igdb.IgdbError as error:
        tags = "" if error.code in NO_LINK_CODES else SAVED_GAMES_LINK_TAG
        messages.error(request, error.message, extra_tags=tags)
        return redirect(failure_url)
    except SaveFailed as error:
        messages.error(request, error.message, extra_tags=SAVED_GAMES_LINK_TAG)
        return redirect(failure_url)

    if not result.created:
        messages.info(request, ALREADY_SAVED_MESSAGE)
        return redirect("games:entry_detail", entry_id=result.entry.pk)
    messages.success(request, f"Added {result.entry.game.name} to your games.")
    return redirect("games:entry_edit", entry_id=result.entry.pk)


def with_saved_entries(user, games) -> list[dict]:
    """Pair each shown result with the user's own entry ID for it, or None.

    One owner-scoped query for the IGDB IDs on this page. Another user's entry for
    the same game never matches, so their entry IDs can't appear on my page.
    """
    saved = dict(
        owned_entries(user)
        .filter(game__igdb_id__in=[game.igdb_id for game in games])
        .values_list("game__igdb_id", "pk")
    )
    return [{"game": game, "saved_entry_id": saved.get(game.igdb_id)} for game in games]


def search_url(q: str, page: int = 1) -> str:
    """IGDB search for `q` at `page`, on our own route. Blank values are left out:
    no `q` for a blank search, and no `page` for page 1."""
    params = {}
    if q:
        params["q"] = q
        if page > 1:
            params["page"] = page
    querystring = f"?{urlencode(params)}" if params else ""
    return reverse("games:search") + querystring
