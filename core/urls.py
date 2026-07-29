from django.urls import path

from . import views

app_name = 'core'

urlpatterns = [
    path('', views.play, name='play'),
    path('status/', views.play_state, name='play_state'),
    path('svar/', views.submit_answer, name='submit_answer'),
    path('vaert/', views.host_panel, name='host_panel'),
    path('vaert/status/', views.host_state, name='host_state'),
    path('vaert/handling/', views.host_action, name='host_action'),
    path('projektor/', views.projector, name='projector'),
    path('projektor/status/', views.projector_state, name='projector_state'),
]
