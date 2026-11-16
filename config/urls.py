from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from games import views as games_views
from games.api import EntryViewSet
from games.forms import LoginForm

api_router = DefaultRouter()
api_router.register("entries", EntryViewSet, basename="api-entry")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include(api_router.urls)),
    path("accounts/signup/", games_views.signup, name="signup"),
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(authentication_form=LoginForm),
        name="login",
    ),
    # Django's LogoutView accepts POST only; GET returns 405.
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("games.urls")),
]
