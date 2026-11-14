from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import SignupForm


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
    return render(request, "games/saved_games.html")


@login_required
def search(request):
    return render(request, "games/search.html")
