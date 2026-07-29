from django.shortcuts import render

from core.views import player_required

# The topics shown as cards on the home page. Entries without a url_name
# render as disabled "coming soon" cards until the feature exists.
TOPICS = [
    {
        'title': 'Quiz',
        'description': 'Musikquizzen – gæt kunstner og årstal.',
        'url_name': 'core:play',
    },
    {
        'title': 'Drinky',
        'description': 'Mål din promille i løbet af aftenen.',
        'url_name': 'drinky:play',
    },
    {
        'title': 'Funstuff3',
        'description': 'Kommer snart …',
        'url_name': None,
    },
]


@player_required
def home(request):
    return render(request, 'pages/home.html', {
        'topics': TOPICS, 'player': request.player,
    })
