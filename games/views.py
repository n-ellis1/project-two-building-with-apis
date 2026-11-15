from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import redirect, render
from django.utils.cache import patch_vary_headers
from django.views.decorators.http import require_http_methods

from .forms import EntryForm, SignupForm
from .models import Entry
from .queries import (
    PAGE_SIZE,
    SORT_LABELS,
    EntryQuery,
    get_owned_entry_or_404,
    owned_entries,
    parse_entry_query,
    parse_page,
    saved_entries,
    saved_games_url,
    user_platforms_played,
    user_themes,
)


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
    """
    paginator = Paginator(saved_entries(user, query), PAGE_SIZE)
    page_obj = paginator.get_page(page_number)
    number = page_obj.number
    return {
        "page_obj": page_obj,
        "query": query,
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
    return render(
        request,
        "games/entry_detail.html",
        {
            "entry": entry,
            "game": entry.game,
            "saved_games_return_url": saved_games_url(query, parse_page(request.GET.get("page"))),
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


@login_required
def search(request):
    return render(request, "games/search.html")
