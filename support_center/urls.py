from django.urls import path

from . import views

app_name = "support_center"

urlpatterns = [
    path("", views.home, name="home"),
    path("articles/<slug:slug>/", views.article_detail, name="article"),
]
