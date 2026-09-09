from django.urls import path

from apps.availability.views import (
    AuditView,
    ExceptionCollectionView,
    ExceptionDeactivateView,
    ExceptionDetailView,
    ExceptionReviewView,
    RuleCollectionView,
    RuleDeactivateView,
    RuleDetailView,
    RuleReviewView,
    SelfExceptionView,
    SelfRuleView,
    SlotDiscoveryView,
    CustomerSlotDiscoveryView,
    OperatingHoursView,
)

from apps.availability.views import SelfRuleDetailView, SelfExceptionDetailView

urlpatterns = [
    path("me/rules/<uuid:pk>/", SelfRuleDetailView.as_view()),
    path("me/rules/<uuid:pk>/deactivate/", SelfRuleDetailView.as_view()),
    path("me/exceptions/<uuid:pk>/deactivate/", SelfExceptionDetailView.as_view()),
    path("rules/", RuleCollectionView.as_view(), name="availability-rule-list"),
    path("rules/<uuid:pk>/", RuleDetailView.as_view(), name="availability-rule-detail"),
    path("rules/<uuid:pk>/review/", RuleReviewView.as_view(), name="availability-rule-review"),
    path(
        "rules/<uuid:pk>/deactivate/",
        RuleDeactivateView.as_view(),
        name="availability-rule-deactivate",
    ),
    path("exceptions/", ExceptionCollectionView.as_view(), name="availability-exception-list"),
    path(
        "exceptions/<uuid:pk>/",
        ExceptionDetailView.as_view(),
        name="availability-exception-detail",
    ),
    path(
        "exceptions/<uuid:pk>/review/",
        ExceptionReviewView.as_view(),
        name="availability-exception-review",
    ),
    path(
        "exceptions/<uuid:pk>/deactivate/",
        ExceptionDeactivateView.as_view(),
        name="availability-exception-deactivate",
    ),
    path("me/rules/", SelfRuleView.as_view(), name="availability-me-rules"),
    path("me/exceptions/", SelfExceptionView.as_view(), name="availability-me-exceptions"),
    path("slots/", SlotDiscoveryView.as_view(), name="availability-slots"),
    path("customer-slots/", CustomerSlotDiscoveryView.as_view(), name="availability-customer-slots"),
    path("operating-hours/<uuid:clinic_id>/", OperatingHoursView.as_view(), name="availability-operating-hours"),
    path("audit/", AuditView.as_view(), name="availability-audit"),
]
