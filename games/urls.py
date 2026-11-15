from django.urls import path

from . import views

app_name = "games"

urlpatterns = [
    path("", views.home, name="home"),
    path("games/", views.saved_games, name="saved_games"),
    path("games/<int:entry_id>/", views.entry_detail, name="entry_detail"),
    path("games/<int:entry_id>/edit/", views.entry_edit, name="entry_edit"),
    path("games/<int:entry_id>/delete/", views.entry_delete, name="entry_delete"),
    path("search/", views.search, name="search"),
    path("search/save/", views.search_save, name="search_save"),
]
