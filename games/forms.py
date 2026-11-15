from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.core.exceptions import ValidationError

from .models import Entry
from .validation import validate_tracking


def _bootstrap_class(widget) -> str:
    if isinstance(widget, forms.CheckboxInput):
        return "form-check-input"
    if isinstance(widget, forms.Select):
        return "form-select"
    return "form-control"


class BootstrapFormMixin:
    """Add Bootstrap's control classes, and is-invalid on fields with errors."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = _bootstrap_class(field.widget)

    def full_clean(self):
        super().full_clean()
        # Errors are known only after cleaning, so mark invalid fields again.
        for name in self.errors:
            if name in self.fields:
                widget = self.fields[name].widget
                widget.attrs["class"] = f"{_bootstrap_class(widget)} is-invalid"


class SignupForm(BootstrapFormMixin, UserCreationForm):
    pass


class LoginForm(BootstrapFormMixin, AuthenticationForm):
    pass


RATING_CHOICES = [("", "Not rated"), *((n, str(n)) for n in range(1, 11))]
DATE_WIDGET_FORMAT = "%Y-%m-%d"


class EntryForm(BootstrapFormMixin, forms.ModelForm):
    """Tracking fields for one of the user's entries, checked by the shared validation."""

    rating = forms.TypedChoiceField(
        choices=RATING_CHOICES, coerce=int, empty_value=None, required=False
    )
    # A plain text field shown as a dropdown, so the shared validation (not the
    # field's choice list) decides which values are allowed, with its own message.
    # The model field still enforces its 200-character limit.
    platform_played = forms.CharField(label="Platform played", required=False, widget=forms.Select)

    class Meta:
        model = Entry
        fields = [
            "status",
            "favorite",
            "rating",
            "platform_played",
            "start_date",
            "finish_date",
            "hours_played",
            "notes",
        ]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}, format=DATE_WIDGET_FORMAT),
            "finish_date": forms.DateInput(attrs={"type": "date"}, format=DATE_WIDGET_FORMAT),
            "hours_played": forms.NumberInput(attrs={"min": "0", "step": "0.1"}),
            "notes": forms.Textarea(attrs={"rows": 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.game = self.instance.game
        # Captured before the form changes the instance: the value that may stay stale.
        self.stored_platform_played = self.instance.platform_played
        self.fields["platform_played"].widget.choices = self._platform_choices()

    def _platform_choices(self):
        names = list(self.game.platforms.values_list("name", flat=True))
        choices = [("", "Not set"), *((name, name) for name in names)]
        stored = self.stored_platform_played
        if stored and stored not in names:
            choices.append((stored, f"{stored} (no longer listed for this game)"))
        return choices

    def clean(self):
        cleaned_data = super().clean()
        try:
            validate_tracking(
                self.game, cleaned_data, stored_platform_played=self.stored_platform_played
            )
        except ValidationError as error:
            self.add_error(None, error)
        return cleaned_data
