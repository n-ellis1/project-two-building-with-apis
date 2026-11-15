from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import redirect, render

from .forms import SignupForm
from .queries import PAGE_SIZE, parse_page, saved_entries


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


@login_required
def search(request):
    return render(request, "games/search.html")
