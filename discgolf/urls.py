from django.urls import path

from . import views

app_name = 'discgolf'

urlpatterns = [
    path('', views.front, name='front'),
    # 'gruppe/start/' must stay above 'gruppe/<code>/' or it would match as a code.
    path('gruppe/start/', views.start_card, name='start_card'),
    path('runde/', views.resume, name='resume'),
    path('gruppe/<str:code>/', views.setup, name='setup'),
    path(
        'gruppe/<str:code>/spiller/<int:player_id>/slet/',
        views.remove_player,
        name='remove_player',
    ),
    path('gruppe/<str:code>/hul/<int:number>/', views.hole, name='hole'),
    path('gruppe/<str:code>/resultat/', views.results, name='results'),
    path('stilling/', views.standings, name='standings'),
]
