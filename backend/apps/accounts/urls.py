from django.urls import path

from apps.accounts.views import (
    LoginView,
    CustomerOtpLoginView,
    CustomerPasswordLoginView,
    CustomerPasswordResetView,
    CustomerRegistrationView,
    PractitionerRegistrationView,
    PractitionerActivationView,
    LogoutView,
    PasswordChangeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    ProfileView,
    RefreshView,
    RegistrationView,
)

urlpatterns = [
    path("register/", RegistrationView.as_view(), name="auth-register"),
    path("login/", LoginView.as_view(), name="auth-login"),
    path("customer-otp-login/", CustomerOtpLoginView.as_view(), name="auth-customer-otp-login"),
    path("customer-login/", CustomerPasswordLoginView.as_view(), name="auth-customer-login"),
    path("customer-password-reset/", CustomerPasswordResetView.as_view(), name="auth-customer-password-reset"),
    path("customer-register/", CustomerRegistrationView.as_view(), name="auth-customer-register"),
    path("practitioner-register/", PractitionerRegistrationView.as_view(), name="auth-practitioner-register"),
    path("practitioner-activate/", PractitionerActivationView.as_view(), name="auth-practitioner-activate"),
    path("refresh/", RefreshView.as_view(), name="auth-refresh"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("password/change/", PasswordChangeView.as_view(), name="auth-password-change"),
    path(
        "password/reset/request/",
        PasswordResetRequestView.as_view(),
        name="auth-password-reset-request",
    ),
    path(
        "password/reset/confirm/",
        PasswordResetConfirmView.as_view(),
        name="auth-password-reset-confirm",
    ),
    path("profile/", ProfileView.as_view(), name="auth-profile"),
]
