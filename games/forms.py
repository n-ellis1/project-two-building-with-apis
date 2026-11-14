from django.contrib.auth.forms import AuthenticationForm, UserCreationForm


class BootstrapFormMixin:
    """Add Bootstrap's form-control class, and is-invalid on fields with errors."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"

    def full_clean(self):
        super().full_clean()
        # Errors are known only after cleaning, so mark invalid fields again.
        for name in self.errors:
            if name in self.fields:
                self.fields[name].widget.attrs["class"] = "form-control is-invalid"


class SignupForm(BootstrapFormMixin, UserCreationForm):
    pass


class LoginForm(BootstrapFormMixin, AuthenticationForm):
    pass
