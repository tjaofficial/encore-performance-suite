from django.urls import path

from . import views

app_name = "marketing"

urlpatterns = [
    path(
        "",
        views.home,
        name="home",
    ),
    path(
        "features/",
        views.features,
        name="features",
    ),
    path(
        "pricing/",
        views.pricing,
        name="pricing",
    ),
    path(
        "contact/",
        views.contact,
        name="contact",
    ),
    path(
        "faq/",
        views.faq,
        name="faq",
    ),
]
