from django.urls import path

from . import views

app_name = "games"

urlpatterns = [
    path("", views.home, name="home"),
    path("games/", views.saved_games, name="saved_games"),
    path("games/<int:entry_id>/", views.entry_detail, name="entry_detail"),
    path("search/", views.search, name="search"),
]
