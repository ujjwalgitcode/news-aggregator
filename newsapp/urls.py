from django.urls import path
from .views import news_list

from django.urls import path
from . import views

urlpatterns = [
    path("", news_list, name="news_list"),
    path("news/", views.news_list, name="news_list"),
]
