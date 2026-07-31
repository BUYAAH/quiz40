import re
from decimal import Decimal
from functools import wraps
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import Avg, Case, CharField, Count, F, Max, Q, Sum, Value, When
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .models import Answer, DrinkyReading, DrinkyRound, Player, Quiz

DRINKY_VALUE_RE = re.compile(r'^\d(\.\d{1,2})?$')
# With ~35 guests some demographic buckets are tiny; suppress any group
# average built from fewer readings than this so no result is identifiable.
DRINKY_MIN_GROUP_SIZE = 2

PLAYER_COOKIE = 'player_token'
COOKIE_MAX_AGE = 60 * 60 * 24 * 60  # 60 days: survives the whole party easily

# Letters (incl. Danish/common European), digits, space, hyphen, apostrophe,
# period. Keeps emoji out of nicknames: avoids MySQL charset surprises and
# keeps the leaderboard readable.
NICKNAME_RE = re.compile(r"^[a-zA-Z0-9æøåÆØÅäöüÄÖÜéÉèÈ' .\-]+$")


def _get_quiz():
    """The active quiz: the most recently created one."""
    return Quiz.objects.order_by('-id').first()


def _get_player(request):
    token = request.COOKIES.get(PLAYER_COOKIE)
    if not token:
        return None
    try:
        return Player.objects.get(token=token)
    except (Player.DoesNotExist, ValidationError, ValueError):
        return None


def _redirect_to_gate(request, gate_url):
    """Send the guest to a gate page (via HX-Redirect for htmx requests, so a
    polled fragment never gets a full page swapped into it), preserving where
    they were headed."""
    if request.headers.get('HX-Request'):
        response = HttpResponse()
        response['HX-Redirect'] = gate_url
        return response
    query = urlencode({'next': request.get_full_path()})
    return redirect(f'{gate_url}?{query}')


def player_required(view):
    """Gate for guest-facing views: attaches ``request.player``, or sends the
    guest to register (no cookie) or finish their demographics (registered but
    incomplete — required before any other feature, not just the quiz)."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        player = _get_player(request)
        if player is None:
            return _redirect_to_gate(request, reverse('welcome'))
        request.player = player
        if not player.demographics_done and request.path != reverse('demographics'):
            return _redirect_to_gate(request, reverse('demographics'))
        return view(request, *args, **kwargs)

    return wrapper


def _state_token(quiz):
    """Changes whenever the guest UI must re-render; polling returns 204 otherwise."""
    return f'{quiz.state}:{quiz.current_question_id}'


def _score_and_rank(player, quiz):
    """Total points and shared-placement rank ("1224" competition ranking).
    Every registered guest counts; those without answers stand at 0."""
    totals = dict(
        Player.objects.annotate(
            total=Sum(
                F('answers__artist_points') + F('answers__year_points'),
                filter=Q(answers__question__quiz=quiz),
            )
        ).values_list('id', 'total')
    )
    totals = {pid: total or 0 for pid, total in totals.items()}
    own = totals[player.id]
    rank = 1 + sum(1 for total in totals.values() if total > own)
    return own, rank, len(totals)


def _render_state(request, quiz, player, saved=False, error=None):
    state = quiz.state
    question = quiz.current_question
    context = {
        'quiz': quiz,
        'player': player,
        'question': question,
        'state_token': _state_token(quiz),
        'saved': saved,
        'error': error,
        'answer': None,
    }
    if question is not None:
        context['answer'] = Answer.objects.filter(
            player=player, question=question
        ).first()
    if state in (Quiz.State.INTERLUDE, Quiz.State.REVEALED, Quiz.State.FINISHED):
        score, rank, player_count = _score_and_rank(player, quiz)
        context.update(score=score, rank=rank, player_count=player_count)
    return render(request, 'core/_state.html', context)


def _safe_next(request):
    """The validated ?next= target (internal URLs only), or ''."""
    next_url = request.POST.get('next') or request.GET.get('next') or ''
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts=None):
        return ''
    return next_url


def _demographics_url(next_url):
    """The demographics URL, carrying ?next= along so it lands where the
    guest was originally headed once they've filled it in."""
    url = reverse('demographics')
    return f'{url}?{urlencode({"next": next_url})}' if next_url else url


def welcome(request):
    """Site-wide registration: one nickname per guest, reused by all features."""
    next_url = _safe_next(request)
    existing = _get_player(request)
    if existing:
        if not existing.demographics_done:
            return redirect(_demographics_url(next_url))
        return redirect(next_url or reverse('pages:home'))

    error = None
    nickname = ''
    if request.method == 'POST':
        nickname = request.POST.get('nickname', '').strip()
        if not nickname:
            error = 'Skriv et navn for at være med.'
        elif len(nickname) > 30:
            error = 'Navnet er for langt (højst 30 tegn).'
        elif not NICKNAME_RE.match(nickname):
            error = 'Brug kun bogstaver, tal og mellemrum i navnet.'
        elif Player.objects.filter(nickname__iexact=nickname).exists():
            error = 'Navnet er allerede taget – vælg et andet.'
        else:
            try:
                player = Player.objects.create(nickname=nickname)
            except IntegrityError:
                error = 'Navnet er allerede taget – vælg et andet.'
            else:
                # On to the demographics step; ?next= survives so a deep link
                # (e.g. the quiz QR code) still ends up where it was headed.
                response = redirect(_demographics_url(next_url))
                response.set_cookie(
                    PLAYER_COOKIE,
                    str(player.token),
                    max_age=COOKIE_MAX_AGE,
                    httponly=True,
                    samesite='Lax',
                )
                return response
    return render(request, 'core/welcome.html', {
        'error': error, 'nickname': nickname, 'next': next_url,
    })


@player_required
def demographics(request):
    """Post-signup demographics for the party stats: required before any
    other feature (enforced by player_required on every guest-facing view)."""
    player = request.player
    next_url = _safe_next(request)
    error = None
    if request.method == 'POST':
        try:
            age = int(request.POST.get('age', ''))
        except ValueError:
            age = None
        try:
            kids = int(request.POST.get('kids', ''))
        except ValueError:
            kids = None
        gender = request.POST.get('gender', '')
        relation = request.POST.get('relation', '')
        if (
            age is not None and 25 <= age <= 75
            and kids is not None and 0 <= kids <= 4
            and gender in Player.Gender.values
            and relation in Player.Relation.values
        ):
            player.age = age
            player.kids = kids
            player.gender = gender
            player.relation = relation
            player.save()
            return redirect(next_url or reverse('pages:home'))
        error = 'Udfyld alle felter for at gemme (alder 25-75, børn 0-4).'
    return render(request, 'core/demographics.html', {
        'player': player,
        'error': error,
        'next': next_url,
        'genders': Player.Gender.choices,
        'relations': Player.Relation.choices,
    })


def _drinky_open_round():
    return DrinkyRound.objects.filter(open=True).first()


def _drinky_state_token(round_obj):
    """Changes only when the open round itself changes (opens/closes) — a
    guest's own submission is rendered directly by the POST, not via polling."""
    return str(round_obj.id) if round_obj is not None else 'closed'


def _render_drinky_state(request, player, round_obj, error=None, saved=False):
    context = {
        'round': round_obj,
        'state_token': _drinky_state_token(round_obj),
        'error': error,
        'saved': saved,
        'reading': None,
    }
    if round_obj is not None:
        context['reading'] = DrinkyReading.objects.filter(round=round_obj, player=player).first()
    return render(request, 'core/_drinky_state.html', context)


@player_required
def drinky(request):
    return render(request, 'core/drinky.html', {'player': request.player})


@player_required
def drinky_state(request):
    round_obj = _drinky_open_round()
    if request.GET.get('s') == _drinky_state_token(round_obj):
        return HttpResponse(status=204)
    return _render_drinky_state(request, request.player, round_obj)


@player_required
@require_POST
def submit_drinky_reading(request):
    player = request.player
    round_obj = _drinky_open_round()
    if round_obj is None:
        # Round closed while they were filling the form in.
        return _render_drinky_state(request, player, None)
    if DrinkyReading.objects.filter(round=round_obj, player=player).exists():
        # One-shot: ignore a resubmit (e.g. a double-tap) rather than error.
        return _render_drinky_state(request, player, round_obj)

    raw_value = request.POST.get('value', '').strip().replace(',', '.')
    value = None
    if DRINKY_VALUE_RE.match(raw_value):
        candidate = Decimal(raw_value)
        if Decimal('0.00') <= candidate <= Decimal('2.99'):
            value = candidate
    if value is None:
        return _render_drinky_state(
            request, player, round_obj,
            error='Skriv en promilleværdi mellem 0.00 og 2.99.',
        )

    DrinkyReading.objects.create(round=round_obj, player=player, value=value)
    return _render_drinky_state(request, player, round_obj, saved=True)


@player_required
def play(request):
    quiz = _get_quiz()
    if quiz is None:
        return render(request, 'core/no_quiz.html')
    return render(request, 'core/play.html', {'quiz': quiz, 'player': request.player})


@player_required
def play_state(request):
    """Polled by the guest page every 2s. Cheap: 204 unless the state changed."""
    quiz = _get_quiz()
    if quiz is None or request.GET.get('s') == _state_token(quiz):
        return HttpResponse(status=204)
    return _render_state(request, quiz, request.player)


@player_required
@require_POST
def submit_answer(request):
    quiz = _get_quiz()
    player = request.player
    if quiz is None:
        return HttpResponse(status=204)
    if quiz.state != Quiz.State.QUESTION_OPEN or quiz.current_question is None:
        # Question closed while they were submitting; show the current state.
        return _render_state(request, quiz, player)

    question = quiz.current_question
    chosen = request.POST.get('option', '')
    valid_options = {option.value for option in question.Option}
    try:
        year = int(request.POST.get('year', ''))
    except ValueError:
        year = None
    if chosen not in valid_options or year is None or not 1000 <= year <= 9999:
        return _render_state(
            request, quiz, player,
            error='Vælg en kunstner og skriv et årstal (fx 1986).',
        )

    Answer.objects.update_or_create(
        player=player,
        question=question,
        defaults={'chosen_option': chosen, 'guessed_year': year},
    )
    return _render_state(request, quiz, player, saved=True)


# --- Host panel ---------------------------------------------------------------


def _next_question(quiz):
    questions = quiz.questions.order_by('order')
    if quiz.current_question_id:
        questions = questions.filter(order__gt=quiz.current_question.order)
    return questions.first()


def _score_current_question(quiz):
    answers = list(quiz.current_question.answers.select_related('question'))
    for answer in answers:
        answer.compute_points()
    Answer.objects.bulk_update(answers, ['artist_points', 'year_points'])


def _apply_host_action(quiz, action):
    """State machine transitions. Invalid (state, action) pairs are ignored,
    so a stale double-click can never skip a step."""
    state = quiz.state
    if action == 'interlude' and state in (Quiz.State.WAITING, Quiz.State.REVEALED):
        next_question = _next_question(quiz)
        if next_question is None:
            quiz.state = Quiz.State.FINISHED
            quiz.current_question = None
        else:
            quiz.current_question = next_question
            quiz.state = Quiz.State.INTERLUDE
    elif action == 'open' and state == Quiz.State.INTERLUDE:
        quiz.state = Quiz.State.QUESTION_OPEN
    elif action == 'close' and state == Quiz.State.QUESTION_OPEN:
        # Lock answers, score them, and reveal in one step.
        quiz.state = Quiz.State.REVEALED
        _score_current_question(quiz)
    elif action == 'back':
        _step_back(quiz)
    else:
        return
    quiz.save()


def _step_back(quiz):
    """Reverse one step of the forward flow. Safe everywhere except one case
    the host must judge: backing from revealed to open lets guests edit
    answers after seeing the facit. Scoring self-heals (recomputed on close)."""
    state = quiz.state
    if state == Quiz.State.FINISHED:
        quiz.current_question = quiz.questions.order_by('-order').first()
        quiz.state = (
            Quiz.State.REVEALED if quiz.current_question else Quiz.State.WAITING
        )
    elif state == Quiz.State.REVEALED:
        # The one host-judgment step: guests have seen the facit and can
        # now edit their answers again.
        quiz.state = Quiz.State.QUESTION_OPEN
    elif state == Quiz.State.QUESTION_OPEN:
        quiz.state = Quiz.State.INTERLUDE
    elif state == Quiz.State.INTERLUDE:
        previous = (
            quiz.questions.filter(order__lt=quiz.current_question.order)
            .order_by('-order')
            .first()
        )
        if previous is None:
            quiz.current_question = None
            quiz.state = Quiz.State.WAITING
        else:
            quiz.current_question = previous
            quiz.state = Quiz.State.REVEALED


def _render_host_state(request, quiz):
    context = {'quiz': quiz, 'question': None}
    if quiz is not None:
        context.update(
            question=quiz.current_question,
            question_count=quiz.questions.count(),
            player_count=Player.objects.count(),
            is_last_question=(
                quiz.current_question is not None and _next_question(quiz) is None
            ),
        )
        if quiz.state == Quiz.State.QUESTION_OPEN:
            context['answered_count'] = quiz.current_question.answers.count()
    return render(request, 'core/_host_state.html', context)


@login_required
def host_panel(request):
    return render(request, 'core/host.html', {'quiz': _get_quiz()})


@login_required
def host_state(request):
    return _render_host_state(request, _get_quiz())


@login_required
@require_POST
def host_action(request):
    quiz = _get_quiz()
    if quiz is not None:
        _apply_host_action(quiz, request.POST.get('action'))
    return _render_host_state(request, quiz)


# --- Projector ----------------------------------------------------------------


def _option_breakdown(question):
    """Per-option answer share for the reveal screen's proportion bars."""
    counts = dict(
        question.answers.values('chosen_option').annotate(n=Count('id')).values_list('chosen_option', 'n')
    )
    total = sum(counts.values())
    return [
        {
            'label': label,
            'count': counts.get(value, 0),
            'pct': round(100 * counts.get(value, 0) / total) if total else 0,
            'correct': value == question.correct_option,
        }
        for value, label in question.options
    ]


def _round_winners(question):
    """Nickname(s) with the most points on this question (shared on a tie);
    empty if nobody scored."""
    answers = list(
        question.answers
        .annotate(round_points=F('artist_points') + F('year_points'))
        .filter(round_points__gt=0)
        .select_related('player')
        .order_by('-round_points')
    )
    if not answers:
        return []
    top = answers[0].round_points
    return [
        {'nickname': answer.player.nickname, 'points': top}
        for answer in answers if answer.round_points == top
    ]


def _leaderboard(quiz, limit=10):
    """Ranked totals with shared placement ("1224" competition ranking).
    All registered guests appear; no answers means 0 points."""
    players = (
        Player.objects
        .annotate(total=Coalesce(
            Sum(
                F('answers__artist_points') + F('answers__year_points'),
                filter=Q(answers__question__quiz=quiz),
            ),
            0,
        ))
        .order_by('-total', 'nickname')
    )
    board = []
    previous_total = None
    rank = 0
    for position, player in enumerate(players, 1):
        if player.total != previous_total:
            rank = position
            previous_total = player.total
        board.append({'rank': rank, 'nickname': player.nickname, 'total': player.total})
    return board[:limit]


def _render_projector_state(request, quiz):
    context = {
        'quiz': quiz,
        'question': quiz.current_question,
        'player_count': Player.objects.count(),
    }
    if quiz.state == Quiz.State.QUESTION_OPEN:
        context['answered_count'] = quiz.current_question.answers.count()
    if quiz.state == Quiz.State.REVEALED:
        context['leaderboard'] = _leaderboard(quiz, limit=3)
        context['option_breakdown'] = _option_breakdown(quiz.current_question)
        context['round_winners'] = _round_winners(quiz.current_question)
    if quiz.state == Quiz.State.FINISHED:
        context['leaderboard'] = _leaderboard(quiz)
    return render(request, 'core/_projector_state.html', context)


def projector(request):
    quiz = _get_quiz()
    if quiz is None:
        return render(request, 'core/no_quiz.html')
    return render(request, 'core/projector.html', {'quiz': quiz})


def projector_state(request):
    quiz = _get_quiz()
    if quiz is None:
        return HttpResponse(status=204)
    return _render_projector_state(request, quiz)


# --- Drinky host panel ---------------------------------------------------------


def _render_drinky_host_state(request):
    rounds = DrinkyRound.objects.order_by('-number')
    open_round = next((round_obj for round_obj in rounds if round_obj.open), None)
    context = {
        'rounds': rounds,
        'open_round': open_round,
        'player_count': Player.objects.count(),
    }
    if open_round is not None:
        context['submitted_count'] = open_round.readings.count()
    return render(request, 'core/_drinky_host_state.html', context)


@login_required
def drinky_host_panel(request):
    return render(request, 'core/drinky_host.html')


@login_required
def drinky_host_state(request):
    return _render_drinky_host_state(request)


@login_required
@require_POST
def drinky_host_action(request):
    action = request.POST.get('action')
    if action == 'create':
        next_number = (DrinkyRound.objects.aggregate(Max('number'))['number__max'] or 0) + 1
        title = request.POST.get('title', '').strip()
        DrinkyRound.objects.create(number=next_number, title=title)
    elif action == 'open':
        round_obj = DrinkyRound.objects.filter(pk=request.POST.get('round_id')).first()
        if round_obj is not None:
            # Only one round is ever open at once.
            DrinkyRound.objects.exclude(pk=round_obj.pk).filter(open=True).update(open=False)
            round_obj.open = True
            round_obj.save(update_fields=['open'])
    elif action == 'close':
        DrinkyRound.objects.filter(pk=request.POST.get('round_id')).update(open=False)
    return _render_drinky_host_state(request)


# --- Drinky results (projector) -------------------------------------------------


def _drinky_series_by(rounds, player_field, value_label_pairs):
    """{label: [avg-or-None per round]} for a Player field, aggregated per round.
    Any (round, group) average built from fewer than DRINKY_MIN_GROUP_SIZE
    readings is dropped so it can't single someone out."""
    rows = (
        DrinkyReading.objects
        .values('round__number', f'player__{player_field}')
        .annotate(avg=Avg('value'), n=Count('id'))
        .filter(n__gte=DRINKY_MIN_GROUP_SIZE)
    )
    lookup = {
        (row['round__number'], row[f'player__{player_field}']): float(row['avg'])
        for row in rows
    }
    return {
        label: [lookup.get((round_obj.number, value)) for round_obj in rounds]
        for value, label in value_label_pairs
    }


DRINKY_AGE_BRACKETS = [
    ('<=35', Q(player__age__lte=35)),
    ('36-40', Q(player__age__gte=36, player__age__lte=40)),
    ('41-45', Q(player__age__gte=41, player__age__lte=45)),
    ('>=46', Q(player__age__gte=46)),
]


def _drinky_age_series(rounds):
    """Same idea as _drinky_series_by, but age is bucketed into brackets
    rather than grouped by a raw field value."""
    bracket = Case(
        *[When(condition, then=Value(label)) for label, condition in DRINKY_AGE_BRACKETS],
        output_field=CharField(),
    )
    rows = (
        DrinkyReading.objects
        .annotate(bracket=bracket)
        .values('round__number', 'bracket')
        .annotate(avg=Avg('value'), n=Count('id'))
        .filter(n__gte=DRINKY_MIN_GROUP_SIZE)
    )
    lookup = {(row['round__number'], row['bracket']): float(row['avg']) for row in rows}
    return {
        label: [lookup.get((round_obj.number, label)) for round_obj in rounds]
        for label, _ in DRINKY_AGE_BRACKETS
    }


def _drinky_chart_data():
    """Aggregate-only chart data for the results page — no individual guest is
    ever named, and any group average built from fewer than
    DRINKY_MIN_GROUP_SIZE readings is dropped so it can't single someone out."""
    rounds = list(DrinkyRound.objects.order_by('number'))
    round_labels = [str(round_obj) for round_obj in rounds]

    overall_lookup = {
        row['round__number']: float(row['avg'])
        for row in DrinkyReading.objects.values('round__number').annotate(avg=Avg('value'))
    }
    overall_series = [overall_lookup.get(round_obj.number) for round_obj in rounds]

    relation_series = _drinky_series_by(rounds, 'relation', Player.Relation.choices)
    gender_series = _drinky_series_by(rounds, 'gender', Player.Gender.choices)
    kids_series = _drinky_series_by(rounds, 'kids', [(kids, str(kids)) for kids in range(5)])
    age_series = _drinky_age_series(rounds)

    return {
        'round_labels': round_labels,
        'overall_series': overall_series,
        'relation_series': relation_series,
        'gender_series': gender_series,
        'age_series': age_series,
        'kids_series': kids_series,
    }


def drinky_projector(request):
    return render(request, 'core/drinky_projector.html', {
        'chart_data': _drinky_chart_data(),
    })
