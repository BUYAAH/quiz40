from django.urls import path

from . import views

app_name = 'drinky'

urlpatterns = [
    path('', views.drinky, name='play'),
    path('status/', views.drinky_state, name='status'),
    path('svar/', views.submit_drinky_reading, name='submit'),
    path('vaert/', views.drinky_host_panel, name='host_panel'),
    path('vaert/status/', views.drinky_host_state, name='host_state'),
    path('vaert/handling/', views.drinky_host_action, name='host_action'),
    path('projektor/', views.drinky_projector, name='projector'),
]
