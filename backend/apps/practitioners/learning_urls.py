from django.urls import path
from .learning import LearningCollection, LearningDetail, LearningAssets, LearningAssetDetail, LearningImageFile
urlpatterns = [path("", LearningCollection.as_view()), path("images/<uuid:pk>/", LearningImageFile.as_view()), path("<uuid:pk>/", LearningDetail.as_view()), path("<uuid:pk>/<str:kind>/", LearningAssets.as_view()), path("<uuid:pk>/<str:kind>/<uuid:asset_pk>/", LearningAssetDetail.as_view())]
