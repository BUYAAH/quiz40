
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include

from core import views as core_views


urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    # Site-wide guest registration; the views live in core (the shared app).
    path('velkommen/', core_views.welcome, name='welcome'),
    path('profil/', core_views.demographics, name='demographics'),
    # Projector arrival screen, belonging to no single feature.
    path('start/', core_views.start, name='start'),
    path('start/status/', core_views.start_state, name='start_state'),
    path('drinky/', include('core.drinky_urls')),
    path('quiz/', include('core.urls')),
    # Temporary for the disc golf event: the site root serves the discgolf
    # front page, and the party home page moves aside to /fest/. Swap these
    # two lines back after the event.
    path('fest/', include('pages.urls')),
    path('', include('discgolf.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
