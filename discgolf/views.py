from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Card, Course, Hole, Player, Score

SESSION_CARD_KEY = 'discgolf_card'


def _course():
    """The event runs on a single course (created in the admin)."""
    return Course.objects.first()


def _get_card(request, code):
    """Fetch a card by its URL code and remember it in the session, so the
    navbar's 'Jeres runde' link can find the way back after e.g. 'Stilling'."""
    card = get_object_or_404(Card, code=code)
    request.session[SESSION_CARD_KEY] = card.code
    return card


def _leaderboard(course):
    """One section per division (only divisions with players), each holding
    complete rounds ranked by total strokes (ties share placement) plus its
    in-progress players."""
    total_holes = course.holes.count()
    total_par = course.total_par
    players = list(
        Player.objects.filter(card__course=course)
        .annotate(total=Sum('scores__strokes'), played=Count('scores'))
        .filter(played__gt=0)
    )
    sections = []
    for division in Player.Division:
        div_players = [p for p in players if p.division == division]
        complete = sorted(
            (p for p in div_players if p.played == total_holes),
            key=lambda p: p.total,
        )
        rows = []
        for i, p in enumerate(complete):
            if i > 0 and p.total == complete[i - 1].total:
                rank = rows[-1]['rank']
            else:
                rank = i + 1
            rows.append({'rank': rank, 'player': p, 'to_par': p.total - total_par})
        in_progress = [p for p in div_players if p.played < total_holes]
        if rows or in_progress:
            sections.append({
                'label': division.label,
                'rows': rows,
                'in_progress': in_progress,
            })
    return sections


def front(request):
    has_card = Card.objects.filter(
        code=request.session.get(SESSION_CARD_KEY, '')
    ).exists()
    return render(request, 'discgolf/front.html', {
        'course': _course(),
        'has_card': has_card,
    })


@require_POST
def start_card(request):
    course = _course()
    if course is None:
        return redirect('discgolf:front')
    card = Card.objects.create(course=course)
    request.session[SESSION_CARD_KEY] = card.code
    return redirect('discgolf:setup', code=card.code)


def resume(request):
    """Jump back into this phone's current round: the first hole missing a
    score, or setup/results when the round hasn't started / is finished."""
    card = Card.objects.filter(
        code=request.session.get(SESSION_CARD_KEY, '')
    ).first()
    if card is None:
        return redirect('discgolf:front')
    players = list(card.players.all())
    if not players:
        return redirect('discgolf:setup', code=card.code)
    counts = dict(
        Score.objects.filter(player__in=players)
        .values_list('hole_id')
        .annotate(n=Count('id'))
        .values_list('hole_id', 'n')
    )
    for hole in card.course.holes.all():
        if counts.get(hole.pk, 0) < len(players):
            return redirect('discgolf:hole', code=card.code, number=hole.number)
    return redirect('discgolf:results', code=card.code)


def setup(request, code):
    card = _get_card(request, code)
    error = ''
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        division = request.POST.get('division', '')
        if division not in Player.Division.values:
            division = Player.Division.ADULT
        if not name:
            error = 'Skriv et navn.'
        elif card.players.filter(name__iexact=name).exists():
            error = 'Der er allerede en spiller med det navn i gruppen.'
        else:
            Player.objects.create(card=card, name=name[:30], division=division)
            return redirect('discgolf:setup', code=card.code)
    return render(request, 'discgolf/setup.html', {
        'card': card,
        'players': card.players.all(),
        'error': error,
        'first_hole': card.course.holes.first(),
        'divisions': Player.Division.choices,
    })


@require_POST
def remove_player(request, code, player_id):
    card = _get_card(request, code)
    get_object_or_404(Player, pk=player_id, card=card).delete()
    return redirect('discgolf:setup', code=card.code)


def hole(request, code, number):
    card = _get_card(request, code)
    hole = get_object_or_404(Hole, course=card.course, number=number)
    players = list(card.players.all())
    if not players:
        return redirect('discgolf:setup', code=card.code)

    existing = {
        s.player_id: s.strokes
        for s in Score.objects.filter(hole=hole, player__in=players)
    }
    error = ''
    entered = {}
    if request.method == 'POST':
        for player in players:
            raw = request.POST.get(f'strokes_{player.pk}', '').strip()
            entered[player.pk] = raw
            try:
                strokes = int(raw)
            except ValueError:
                error = 'Skriv antal kast for alle spillere.'
                continue
            if not 1 <= strokes <= 30:
                error = 'Antal kast skal være mellem 1 og 30.'
                continue
            entered[player.pk] = strokes
        if not error:
            for player in players:
                Score.objects.update_or_create(
                    player=player, hole=hole,
                    defaults={'strokes': entered[player.pk]},
                )
            next_hole = (
                card.course.holes.filter(number__gt=hole.number)
                .order_by('number').first()
            )
            if next_hole:
                return redirect('discgolf:hole', code=card.code, number=next_hole.number)
            return redirect('discgolf:results', code=card.code)

    rows = [
        {'player': p, 'strokes': entered.get(p.pk, existing.get(p.pk, ''))}
        for p in players
    ]
    prev_hole = (
        card.course.holes.filter(number__lt=hole.number).order_by('-number').first()
    )
    return render(request, 'discgolf/hole.html', {
        'card': card,
        'hole': hole,
        'rows': rows,
        'error': error,
        'prev_hole': prev_hole,
        'hole_count': card.course.holes.count(),
        'is_last': not card.course.holes.filter(number__gt=hole.number).exists(),
    })


def results(request, code):
    card = _get_card(request, code)
    holes = list(card.course.holes.all())
    scores = {
        (s.player_id, s.hole_id): s.strokes
        for s in Score.objects.filter(player__card=card)
    }
    total_par = card.course.total_par
    rows = []
    for player in card.players.all():
        cells = [scores.get((player.pk, h.pk)) for h in holes]
        played = [c for c in cells if c is not None]
        total = sum(played)
        rows.append({
            'player': player,
            'cells': cells,
            'total': total,
            'to_par': total - total_par if len(played) == len(holes) else None,
        })
    rows.sort(key=lambda r: (r['to_par'] is None, r['total']))
    return render(request, 'discgolf/results.html', {
        'card': card,
        'holes': holes,
        'rows': rows,
        'sections': _leaderboard(card.course),
    })


def standings(request):
    course = _course()
    return render(request, 'discgolf/standings.html', {
        'course': course,
        'sections': _leaderboard(course) if course else [],
    })
