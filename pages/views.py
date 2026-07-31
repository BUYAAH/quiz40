from django.shortcuts import render

from core.views import player_required

# The topics shown as cards on the home page. Entries without a url_name
# render as disabled "coming soon" cards until the feature exists.
TOPICS = [
    {
        'title': 'Quiz',
        'url_name': 'core:play',
    },
    {
        'title': 'Drinky',
        'url_name': 'drinky:play',
    },
]


@player_required
def home(request):
    return render(request, 'pages/home.html', {
        'topics': TOPICS, 'player': request.player,
    })
