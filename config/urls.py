from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from games import views as games_views
from games.forms import LoginForm

urlpatterns = [
    path("admin/", admin.site.urls),
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
