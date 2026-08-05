from django.urls import path

from apps.accounts.access_views import (
    AccessSummaryView,
    RoleActivateView,
    RoleCollectionView,
    RoleDeactivateView,
    RoleDetailView,
)

urlpatterns = [
    path("me/", AccessSummaryView.as_view(), name="access-me"),
    path("roles/", RoleCollectionView.as_view(), name="access-role-list"),
    path("roles/<uuid:pk>/", RoleDetailView.as_view(), name="access-role-detail"),
    path("roles/<uuid:pk>/activate/", RoleActivateView.as_view(), name="access-role-activate"),
    path(
        "roles/<uuid:pk>/deactivate/",
        RoleDeactivateView.as_view(),
        name="access-role-deactivate",
    ),
]
