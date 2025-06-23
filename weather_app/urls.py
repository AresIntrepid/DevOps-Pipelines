#URL routing specific to the weather app

from django.urls import path
from . import views #import views from current directory(app)

#URL pattern for weather app
urlpatterns = [
    #home page
    path('', views.index, name = 'index'),
    #api endpoints
    path('random-weather/', views.get_random_weather, name = 'random_weather'), #API: /random-weather/
    path('cache-stats/', views.cache_stats, name ='cache_stats'), #cache stats api
    #dashborad endpoints
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('api/dashboard-stats/', views.dashboard_stats_api, name='dashboard_stats'),
]

