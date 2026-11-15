from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from .forms import EntryForm, SignupForm
from .queries import PAGE_SIZE, get_owned_entry_or_404, parse_page, saved_entries


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


@login_required
def saved_games(request):
    """My Saved Games, read only from SQLite (never contacts IGDB)."""
    paginator = Paginator(saved_entries(request.user), PAGE_SIZE)
    page_obj = paginator.get_page(parse_page(request.GET.get("page")))
    return render(request, "games/saved_games.html", {"page_obj": page_obj})


def saved_games_url(page: int) -> str:
    """My Saved Games at `page`, built from our own route (no `?page` for page 1)."""
    url = reverse("games:saved_games")
    return f"{url}?page={page}" if page > 1 else url


@login_required
def entry_detail(request, entry_id):
    """One of my entries, read only from SQLite. Anyone else's entry ID is a 404.

    `?page` is the My Saved Games page the entry was opened from. It only ever
    becomes a validated page number on our own route (Phase 6 adds the rest of
    the list's query state).
    """
    entry = get_owned_entry_or_404(request.user, entry_id)
    return render(
        request,
        "games/entry_detail.html",
        {
            "entry": entry,
            "game": entry.game,
            "saved_games_return_url": saved_games_url(parse_page(request.GET.get("page"))),
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
