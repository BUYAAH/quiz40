from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .models import Answer, DrinkyReading, DrinkyRound, Player, Question, Quiz
from .views import PLAYER_COOKIE


def make_quiz(state=Quiz.State.WAITING):
    quiz = Quiz.objects.create(name='Testquiz', state=state)
    question = Question.objects.create(
        quiz=quiz, order=1,
        option_a='ABBA', option_b='Queen', option_c='Prince', option_d='TLC',
        correct_option='b', correct_year=1986,
    )
    return quiz, question


def make_player(nickname='Marti', with_demographics=True):
    """Most guest-facing views require demographics to be filled in (the
    player_required gate); tests that aren't specifically about that gate
    use a player who's already past it."""
    player = Player.objects.create(nickname=nickname)
    if with_demographics:
        player.age = 39
        player.gender = 'm'
        player.kids = 3
        player.relation = 'friend'
        player.save()
    return player


class WelcomeTests(TestCase):
    def test_registration_creates_player_and_continues_to_demographics(self):
        response = self.client.post(reverse('welcome'), {'nickname': 'Marti'})
        self.assertRedirects(response, reverse('demographics'))
        player = Player.objects.get()
        self.assertEqual(player.nickname, 'Marti')
        self.assertEqual(response.cookies[PLAYER_COOKIE].value, str(player.token))

    def test_next_param_carried_through_demographics(self):
        response = self.client.post(
            reverse('welcome'), {'nickname': 'Marti', 'next': reverse('core:play')}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url, reverse('demographics') + '?next=%2Fquiz%2F'
        )

    def test_external_next_ignored(self):
        response = self.client.post(
            reverse('welcome'), {'nickname': 'Marti', 'next': 'https://evil.example/'}
        )
        self.assertRedirects(response, reverse('demographics'))

    def test_duplicate_nickname_rejected(self):
        Player.objects.create(nickname='Marti')
        response = self.client.post(reverse('welcome'), {'nickname': 'marti'})
        self.assertContains(response, 'allerede taget')
        self.assertEqual(Player.objects.count(), 1)

    def test_emoji_nickname_rejected(self):
        response = self.client.post(reverse('welcome'), {'nickname': '🎉Fest🎉'})
        self.assertContains(response, 'kun bogstaver')
        self.assertEqual(Player.objects.count(), 0)

    def test_danish_letters_accepted(self):
        response = self.client.post(
            reverse('welcome'), {'nickname': 'Søren-Åge d. 3.'}
        )
        self.assertRedirects(response, reverse('demographics'))

    def test_returning_player_without_demographics_sent_there(self):
        player = make_player(with_demographics=False)
        self.client.cookies[PLAYER_COOKIE] = str(player.token)
        response = self.client.get(reverse('welcome'))
        self.assertRedirects(response, reverse('demographics'))

    def test_returning_player_with_demographics_skips_registration(self):
        player = make_player()
        self.client.cookies[PLAYER_COOKIE] = str(player.token)
        response = self.client.get(reverse('welcome'))
        self.assertRedirects(response, reverse('pages:home'))

    def test_home_gated_without_cookie(self):
        response = self.client.get(reverse('pages:home'))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse('welcome')))

    def test_home_gated_without_demographics(self):
        player = make_player(with_demographics=False)
        self.client.cookies[PLAYER_COOKIE] = str(player.token)
        response = self.client.get(reverse('pages:home'))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse('demographics')))

    def test_no_quiz_shows_friendly_page(self):
        player = make_player()
        self.client.cookies[PLAYER_COOKIE] = str(player.token)
        response = self.client.get(reverse('core:play'))
        self.assertContains(response, 'ikke klar')


class DemographicsTests(TestCase):
    def setUp(self):
        self.player = make_player(with_demographics=False)
        self.client.cookies[PLAYER_COOKIE] = str(self.player.token)

    def test_save_all_fields_and_redirect_home(self):
        response = self.client.post(reverse('demographics'), {
            'age': 39, 'gender': 'm', 'kids': 3, 'relation': 'friend',
        })
        self.assertRedirects(response, reverse('pages:home'))
        self.player.refresh_from_db()
        self.assertEqual(
            (self.player.age, self.player.gender, self.player.kids, self.player.relation),
            (39, 'm', 3, 'friend'),
        )
        self.assertTrue(self.player.demographics_done)

    def test_next_param_respected_after_save(self):
        response = self.client.post(reverse('demographics'), {
            'age': 39, 'gender': 'm', 'kids': 3, 'relation': 'friend',
            'next': reverse('core:play'),
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('core:play'))

    def test_incomplete_form_shows_error_and_saves_nothing(self):
        response = self.client.post(reverse('demographics'), {
            'age': 39, 'gender': 'm', 'kids': '', 'relation': 'friend',
        })
        self.assertContains(response, 'Udfyld alle felter')
        self.player.refresh_from_db()
        self.assertIsNone(self.player.age)
        self.assertFalse(self.player.demographics_done)

    def test_invalid_choice_rejected(self):
        response = self.client.post(reverse('demographics'), {
            'age': 39, 'gender': 'q', 'kids': 3, 'relation': 'friend',
        })
        self.assertContains(response, 'Udfyld alle felter')
        self.player.refresh_from_db()
        self.assertFalse(self.player.demographics_done)

    def test_out_of_range_values_rejected(self):
        for field, value in (('age', 24), ('age', 76), ('kids', 5)):
            data = {'age': 39, 'gender': 'm', 'kids': 3, 'relation': 'friend'}
            data[field] = value
            response = self.client.post(reverse('demographics'), data)
            self.assertContains(response, 'Udfyld alle felter', msg_prefix=f'{field}={value}')
        self.player.refresh_from_db()
        self.assertFalse(self.player.demographics_done)

    def test_form_prefills_existing_values(self):
        Player.objects.filter(pk=self.player.pk).update(
            age=39, gender='m', kids=3, relation='friend',
        )
        response = self.client.get(reverse('demographics'))
        self.assertContains(response, 'value="39"')

    def test_home_gated_until_done_then_reachable(self):
        response = self.client.get(reverse('pages:home'))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse('demographics')))

        Player.objects.filter(pk=self.player.pk).update(
            age=39, gender='m', kids=3, relation='friend',
        )
        response = self.client.get(reverse('pages:home'))
        self.assertEqual(response.status_code, 200)

    def test_home_offers_no_edit_link_but_direct_resave_still_works(self):
        """By design there is no way back to the profile from home: a misclick
        stands. The view itself still accepts a re-save if reached directly."""
        Player.objects.filter(pk=self.player.pk).update(
            age=39, gender='m', kids=3, relation='friend',
        )
        response = self.client.get(reverse('pages:home'))
        self.assertNotContains(response, reverse('demographics'))

        response = self.client.post(reverse('demographics'), {
            'age': 40, 'gender': 'm', 'kids': 3, 'relation': 'badminton',
        })
        self.assertRedirects(response, reverse('pages:home'))
        self.player.refresh_from_db()
        self.assertEqual((self.player.age, self.player.relation), (40, 'badminton'))


class PlayTests(TestCase):
    def setUp(self):
        self.quiz, self.question = make_quiz(Quiz.State.QUESTION_OPEN)
        self.quiz.current_question = self.question
        self.quiz.save()
        self.player = make_player()
        self.client.cookies[PLAYER_COOKIE] = str(self.player.token)

    def test_play_without_cookie_redirects_to_welcome(self):
        self.client.cookies.pop(PLAYER_COOKIE)
        response = self.client.get(reverse('core:play'))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse('welcome')))

    def test_htmx_poll_without_cookie_gets_hx_redirect(self):
        self.client.cookies.pop(PLAYER_COOKIE)
        response = self.client.get(
            reverse('core:play_state'), headers={'HX-Request': 'true'}
        )
        self.assertEqual(response.headers['HX-Redirect'], reverse('welcome'))

    def test_play_without_demographics_redirects_there(self):
        incomplete = make_player(nickname='Ny gæst', with_demographics=False)
        self.client.cookies[PLAYER_COOKIE] = str(incomplete.token)
        response = self.client.get(reverse('core:play'))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse('demographics')))

    def test_interlude_shows_title_on_phone(self):
        self.quiz.state = Quiz.State.INTERLUDE
        self.quiz.save()
        self.question.interlude_title = 'Dengang i 1986'
        self.question.save()
        response = self.client.get(reverse('core:play_state'))
        self.assertContains(response, 'Dengang i 1986')

    def test_interlude_without_extras_shows_look_up_message(self):
        self.quiz.state = Quiz.State.INTERLUDE
        self.quiz.save()
        response = self.client.get(reverse('core:play_state'))
        self.assertContains(response, 'Kig op')

    def test_open_question_shows_answer_form(self):
        response = self.client.get(reverse('core:play_state'))
        self.assertContains(response, 'Hvem er artisten bag nummeret?')
        self.assertContains(response, 'Queen')

    def test_poll_returns_204_when_state_unchanged(self):
        token = f'{self.quiz.state}:{self.question.id}'
        response = self.client.get(reverse('core:play_state'), {'s': token})
        self.assertEqual(response.status_code, 204)

    def test_submit_and_change_answer(self):
        url = reverse('core:submit_answer')
        response = self.client.post(url, {'option': 'b', 'year': 1988})
        self.assertContains(response, 'gemt')
        answer = Answer.objects.get(player=self.player)
        self.assertEqual(answer.chosen_option, 'b')
        self.assertEqual(answer.guessed_year, 1988)

        self.client.post(url, {'option': 'a', 'year': 1985})
        answer.refresh_from_db()
        self.assertEqual(answer.chosen_option, 'a')
        self.assertEqual(answer.guessed_year, 1985)
        self.assertEqual(Answer.objects.count(), 1)

    def test_submit_invalid_year_shows_error(self):
        response = self.client.post(
            reverse('core:submit_answer'), {'option': 'b', 'year': 'nej'}
        )
        self.assertContains(response, 'årstal')
        self.assertEqual(Answer.objects.count(), 0)

    def test_submit_after_reveal_saves_nothing(self):
        self.quiz.state = Quiz.State.REVEALED
        self.quiz.save()
        self.client.post(reverse('core:submit_answer'), {'option': 'b', 'year': 1988})
        self.assertEqual(Answer.objects.count(), 0)


class HostPanelTests(TestCase):
    def setUp(self):
        self.quiz, self.q1 = make_quiz()
        self.q2 = Question.objects.create(
            quiz=self.quiz, order=2,
            option_a='Cher', option_b='Madonna', option_c='Sade', option_d='Enya',
            correct_option='b', correct_year=1990,
        )
        host = get_user_model().objects.create_user('host', password='pw')
        self.client.force_login(host)

    def action(self, name):
        return self.client.post(reverse('core:host_action'), {'action': name})

    def test_panel_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('core:host_panel'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_full_state_cycle(self):
        self.action('interlude')
        self.quiz.refresh_from_db()
        self.assertEqual(self.quiz.state, Quiz.State.INTERLUDE)
        self.assertEqual(self.quiz.current_question, self.q1)

        self.action('open')
        self.quiz.refresh_from_db()
        self.assertEqual(self.quiz.state, Quiz.State.QUESTION_OPEN)

        self.action('close')
        self.quiz.refresh_from_db()
        self.assertEqual(self.quiz.state, Quiz.State.REVEALED)

        self.action('interlude')
        self.quiz.refresh_from_db()
        self.assertEqual(self.quiz.current_question, self.q2)
        self.assertEqual(self.quiz.state, Quiz.State.INTERLUDE)

    def test_finishes_after_last_question(self):
        self.quiz.state = Quiz.State.REVEALED
        self.quiz.current_question = self.q2
        self.quiz.save()
        self.action('interlude')
        self.quiz.refresh_from_db()
        self.assertEqual(self.quiz.state, Quiz.State.FINISHED)
        self.assertIsNone(self.quiz.current_question)

    def test_invalid_action_for_state_is_ignored(self):
        self.action('close')  # quiz is 'waiting'; close is not legal here
        self.quiz.refresh_from_db()
        self.assertEqual(self.quiz.state, Quiz.State.WAITING)

    def test_close_computes_points(self):
        player = Player.objects.create(nickname='Gæst')
        self.quiz.state = Quiz.State.QUESTION_OPEN
        self.quiz.current_question = self.q1
        self.quiz.save()
        answer = Answer.objects.create(
            player=player, question=self.q1, chosen_option='b', guessed_year=1988,
        )
        self.action('close')
        answer.refresh_from_db()
        self.assertEqual(answer.artist_points, 5)
        self.assertEqual(answer.year_points, 3)

    def set_state(self, state, question):
        self.quiz.state = state
        self.quiz.current_question = question
        self.quiz.save()

    def test_back_reverses_each_state(self):
        self.set_state(Quiz.State.REVEALED, self.q1)
        self.action('back')
        self.quiz.refresh_from_db()
        self.assertEqual(self.quiz.state, Quiz.State.QUESTION_OPEN)

        self.action('back')
        self.quiz.refresh_from_db()
        self.assertEqual(self.quiz.state, Quiz.State.INTERLUDE)

    def test_back_from_first_interlude_returns_to_waiting(self):
        self.set_state(Quiz.State.INTERLUDE, self.q1)
        self.action('back')
        self.quiz.refresh_from_db()
        self.assertEqual(self.quiz.state, Quiz.State.WAITING)
        self.assertIsNone(self.quiz.current_question)

    def test_back_from_interlude_reaches_previous_reveal(self):
        self.set_state(Quiz.State.INTERLUDE, self.q2)
        self.action('back')
        self.quiz.refresh_from_db()
        self.assertEqual(self.quiz.state, Quiz.State.REVEALED)
        self.assertEqual(self.quiz.current_question, self.q1)

    def test_back_from_finished_restores_last_question(self):
        self.set_state(Quiz.State.FINISHED, None)
        self.action('back')
        self.quiz.refresh_from_db()
        self.assertEqual(self.quiz.state, Quiz.State.REVEALED)
        self.assertEqual(self.quiz.current_question, self.q2)

    def test_back_from_waiting_is_noop(self):
        self.action('back')
        self.quiz.refresh_from_db()
        self.assertEqual(self.quiz.state, Quiz.State.WAITING)

    def test_answered_counter_shown_while_open(self):
        player = Player.objects.create(nickname='Gæst')
        self.quiz.state = Quiz.State.QUESTION_OPEN
        self.quiz.current_question = self.q1
        self.quiz.save()
        Answer.objects.create(
            player=player, question=self.q1, chosen_option='a', guessed_year=1990,
        )
        response = self.client.get(reverse('core:host_state'))
        self.assertContains(response, 'har svaret')
        self.assertContains(response, '<strong>1</strong>')


class ProjectorTests(TestCase):
    def setUp(self):
        self.quiz, self.question = make_quiz(Quiz.State.REVEALED)
        self.quiz.current_question = self.question
        self.quiz.save()

    def test_projector_needs_no_login(self):
        response = self.client.get(reverse('core:projector'))
        self.assertEqual(response.status_code, 200)

    def test_interlude_shows_numbered_title(self):
        self.quiz.state = Quiz.State.INTERLUDE
        self.quiz.save()
        self.question.interlude_title = 'Dengang i 1986'
        self.question.save()
        response = self.client.get(reverse('core:projector_state'))
        self.assertContains(response, '1: Dengang i 1986')

    def test_interlude_without_title_or_image_falls_back_to_quiz_name(self):
        self.quiz.state = Quiz.State.INTERLUDE
        self.quiz.save()
        response = self.client.get(reverse('core:projector_state'))
        self.assertContains(response, self.quiz.name)

    def test_leaderboard_shares_placement_on_ties(self):
        for nickname, artist_points in (('Anna', 5), ('Bo', 5), ('Carl', 0)):
            player = Player.objects.create(nickname=nickname)
            Answer.objects.create(
                player=player, question=self.question,
                chosen_option='b', guessed_year=1986,
                artist_points=artist_points, year_points=0,
            )
        # Registered but never answered: appears with 0 points, tied with Carl.
        Player.objects.create(nickname='Dora')
        response = self.client.get(reverse('core:projector_state'))
        from .views import _leaderboard
        board = _leaderboard(self.quiz)
        self.assertEqual(
            [(row['rank'], row['nickname']) for row in board],
            [(1, 'Anna'), (1, 'Bo'), (3, 'Carl'), (3, 'Dora')],
        )
        self.assertContains(response, 'Anna')


class ScoringTests(TestCase):
    def test_compute_points(self):
        quiz, question = make_quiz()
        player = Player.objects.create(nickname='Marti')
        cases = [
            # (option, year, artist_points, year_points)
            ('b', 1986, 5, 5),   # both exact
            ('b', 1987, 5, 4),   # +-1
            ('a', 1984, 0, 3),   # wrong artist, +-2
            ('b', 1991, 5, 0),   # +-5
            ('a', 2020, 0, 0),   # everything wrong
        ]
        for option, year, expected_artist, expected_year in cases:
            answer = Answer(
                player=player, question=question,
                chosen_option=option, guessed_year=year,
            )
            answer.compute_points()
            self.assertEqual(answer.artist_points, expected_artist, (option, year))
            self.assertEqual(answer.year_points, expected_year, (option, year))


class DrinkyGuestTests(TestCase):
    def setUp(self):
        self.player = make_player()
        self.client.cookies[PLAYER_COOKIE] = str(self.player.token)

    def test_no_open_round_shows_waiting_message(self):
        response = self.client.get(reverse('drinky:status'))
        self.assertContains(response, 'Intet åbent lige nu')

    def test_open_round_shows_form(self):
        DrinkyRound.objects.create(number=1, open=True)
        response = self.client.get(reverse('drinky:status'))
        self.assertContains(response, 'Runde 1')
        self.assertContains(response, '<form')

    def test_valid_reading_saved(self):
        round_obj = DrinkyRound.objects.create(number=1, open=True)
        response = self.client.post(reverse('drinky:submit'), {'value': '1.23'})
        self.assertContains(response, '1.23')
        reading = DrinkyReading.objects.get(round=round_obj, player=self.player)
        self.assertEqual(str(reading.value), '1.23')

    def test_out_of_range_reading_rejected(self):
        DrinkyRound.objects.create(number=1, open=True)
        response = self.client.post(reverse('drinky:submit'), {'value': '3.00'})
        self.assertContains(response, 'mellem 0.00 og 2.99')
        self.assertEqual(DrinkyReading.objects.count(), 0)

    def test_garbage_reading_rejected(self):
        DrinkyRound.objects.create(number=1, open=True)
        response = self.client.post(reverse('drinky:submit'), {'value': 'abc'})
        self.assertContains(response, 'mellem 0.00 og 2.99')
        self.assertEqual(DrinkyReading.objects.count(), 0)

    def test_resubmit_ignored_one_shot(self):
        round_obj = DrinkyRound.objects.create(number=1, open=True)
        DrinkyReading.objects.create(round=round_obj, player=self.player, value='1.00')
        response = self.client.post(reverse('drinky:submit'), {'value': '2.00'})
        self.assertContains(response, '1.00')
        self.assertEqual(DrinkyReading.objects.count(), 1)

    def test_submit_without_open_round_shows_waiting_message(self):
        response = self.client.post(reverse('drinky:submit'), {'value': '1.00'})
        self.assertContains(response, 'Intet åbent lige nu')
        self.assertEqual(DrinkyReading.objects.count(), 0)

    def test_drinky_gated_without_demographics(self):
        player = make_player(nickname='Nypaa', with_demographics=False)
        self.client.cookies[PLAYER_COOKIE] = str(player.token)
        response = self.client.get(reverse('drinky:play'))
        self.assertRedirects(response, reverse('demographics') + '?next=%2Fdrinky%2F')


class DrinkyHostTests(TestCase):
    def setUp(self):
        host = get_user_model().objects.create_user('host', password='pw')
        self.client.force_login(host)

    def action(self, **data):
        return self.client.post(reverse('drinky:host_action'), data)

    def test_panel_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('drinky:host_panel'))
        self.assertEqual(response.status_code, 302)

    def test_create_round_auto_numbers(self):
        self.action(action='create')
        self.action(action='create')
        numbers = list(DrinkyRound.objects.order_by('number').values_list('number', flat=True))
        self.assertEqual(numbers, [1, 2])

    def test_create_round_with_title(self):
        self.action(action='create', title='15.00')
        round_obj = DrinkyRound.objects.get()
        self.assertEqual(round_obj.title, '15.00')
        self.assertEqual(str(round_obj), '15.00')

    def test_create_round_without_title_falls_back_to_number(self):
        self.action(action='create')
        round_obj = DrinkyRound.objects.get()
        self.assertEqual(round_obj.title, '')
        self.assertEqual(str(round_obj), 'Runde 1')

    def test_opening_a_round_closes_any_other_open_round(self):
        r1 = DrinkyRound.objects.create(number=1, open=True)
        r2 = DrinkyRound.objects.create(number=2)
        self.action(action='open', round_id=r2.id)
        r1.refresh_from_db()
        r2.refresh_from_db()
        self.assertFalse(r1.open)
        self.assertTrue(r2.open)

    def test_close_round(self):
        r1 = DrinkyRound.objects.create(number=1, open=True)
        self.action(action='close', round_id=r1.id)
        r1.refresh_from_db()
        self.assertFalse(r1.open)

    def test_submitted_counter(self):
        round_obj = DrinkyRound.objects.create(number=1, open=True)
        for nickname in ('Anna', 'Bo'):
            DrinkyReading.objects.create(
                round=round_obj, player=make_player(nickname=nickname), value='1.00'
            )
        make_player(nickname='Carl')  # registered, hasn't submitted
        response = self.client.get(reverse('drinky:host_state'))
        self.assertContains(response, '2</strong> af 3 har indtastet')


class DrinkyResultsTests(TestCase):
    def setUp(self):
        self.p1 = make_player(nickname='P1')
        self.p1.kids, self.p1.gender, self.p1.relation, self.p1.age = 0, 'm', 'friend', 30
        self.p1.save()
        self.p2 = make_player(nickname='P2')
        self.p2.kids, self.p2.gender, self.p2.relation, self.p2.age = 0, 'f', 'friend', 32
        self.p2.save()
        self.p3 = make_player(nickname='P3')
        self.p3.kids, self.p3.gender, self.p3.relation, self.p3.age = 2, 'm', 'family', 44
        self.p3.save()
        self.p4 = make_player(nickname='P4')
        self.p4.kids, self.p4.gender, self.p4.relation, self.p4.age = 2, 'f', 'family', 45
        self.p4.save()

        self.r1 = DrinkyRound.objects.create(number=1)
        self.r2 = DrinkyRound.objects.create(number=2)
        readings = {
            (self.r1, self.p1): '1.00', (self.r1, self.p2): '1.20',
            (self.r1, self.p3): '0.50', (self.r1, self.p4): '0.70',
            (self.r2, self.p1): '1.50', (self.r2, self.p2): '1.70',
            (self.r2, self.p3): '0.90', (self.r2, self.p4): '1.10',
        }
        for (round_obj, player), value in readings.items():
            DrinkyReading.objects.create(round=round_obj, player=player, value=value)

    def series(self, data, key):
        """Chart series are ordered [[label, values], ...] lists so the x-axis
        order survives JSON; the assertions below only need lookup by label."""
        self.assertIsInstance(data[key], list)
        return dict(data[key])

    def bucket_of(self, player, brackets):
        """The bracket label this player's readings land in, asked of the same
        CASE expression the charts use. Lets the tests below say "the bucket p1
        is in" instead of hardcoding a label, so re-tuning the brackets moves
        the fixtures to another bucket rather than breaking the assertions."""
        from .views import _bracket_case
        return (
            DrinkyReading.objects
            .filter(player=player)
            .annotate(bracket=_bracket_case(brackets))
            .values_list('bracket', flat=True)
            .first()
        )

    def test_projector_needs_no_login(self):
        response = self.client.get(reverse('drinky:projector'))
        self.assertEqual(response.status_code, 200)

    def test_no_rounds_shows_placeholder(self):
        DrinkyReading.objects.all().delete()
        DrinkyRound.objects.all().delete()
        response = self.client.get(reverse('drinky:projector'))
        self.assertContains(response, 'Ingen data endnu')

    def test_overall_series_averages_each_round(self):
        from .views import _drinky_chart_data
        data = _drinky_chart_data()
        self.assertEqual(data['round_labels'], ['Runde 1', 'Runde 2'])
        self.assertAlmostEqual(data['overall_series'][0], 0.85)
        self.assertAlmostEqual(data['overall_series'][1], 1.30)

    def test_relation_series_grouped_correctly(self):
        from .views import _drinky_chart_data
        data = _drinky_chart_data()
        relation = self.series(data, 'relation_series')
        self.assertAlmostEqual(relation['Ven'][0], 1.10)
        self.assertAlmostEqual(relation['Familie'][0], 0.60)
        self.assertIsNone(relation['Badminton'][0])

    def test_kids_series_grouped_per_round(self):
        from .views import DRINKY_KIDS_BRACKETS, _drinky_chart_data
        data = _drinky_chart_data()
        kids = self.series(data, 'kids_series')
        childless = self.bucket_of(self.p1, DRINKY_KIDS_BRACKETS)  # p1, p2: 0 kids
        two_kids = self.bucket_of(self.p3, DRINKY_KIDS_BRACKETS)   # p3, p4: 2 kids
        self.assertNotEqual(childless, two_kids)
        self.assertAlmostEqual(kids[childless][0], 1.10)
        self.assertAlmostEqual(kids[childless][1], 1.60)
        self.assertAlmostEqual(kids[two_kids][0], 0.60)
        self.assertAlmostEqual(kids[two_kids][1], 1.00)
        for label, _ in DRINKY_KIDS_BRACKETS:
            if label not in (childless, two_kids):
                self.assertEqual(kids[label], [None, None])

    def test_series_keep_their_bracket_order(self):
        # The x-axis order comes straight from this list. Emitted as a JSON
        # object instead, JavaScript would hoist an index-like label such as
        # "2" ahead of "0-1" and "3+" when reading the keys back.
        from .views import DRINKY_AGE_BRACKETS, DRINKY_KIDS_BRACKETS, _drinky_chart_data
        data = _drinky_chart_data()
        for key, brackets in (
            ('kids_series', DRINKY_KIDS_BRACKETS),
            ('age_series', DRINKY_AGE_BRACKETS),
        ):
            self.assertIsInstance(data[key], list)
            self.assertEqual(
                [label for label, _ in data[key]],
                [label for label, _ in brackets],
            )

    def test_kids_brackets_cover_every_allowed_count(self):
        # Same gap guard as the age brackets: a kid count matching no bracket
        # would drop those guests from the chart with no error.
        from .views import DRINKY_KIDS_BRACKETS, _bracket_case
        round_obj = DrinkyRound.objects.create(number=99)
        for kids in range(5):
            player = make_player(nickname=f'Kids{kids}')
            player.kids = kids
            player.save()
            DrinkyReading.objects.create(round=round_obj, player=player, value='1.00')
        uncovered = (
            DrinkyReading.objects
            .filter(round=round_obj)
            .annotate(bracket=_bracket_case(DRINKY_KIDS_BRACKETS))
            .filter(bracket__isnull=True)
            .values_list('player__kids', flat=True)
        )
        self.assertEqual(sorted(uncovered), [])

    def test_gender_series_grouped_per_round(self):
        from .views import _drinky_chart_data
        data = _drinky_chart_data()
        gender = self.series(data, 'gender_series')
        self.assertAlmostEqual(gender['Mand'][0], 0.75)
        self.assertAlmostEqual(gender['Mand'][1], 1.20)
        self.assertAlmostEqual(gender['Kvinde'][0], 0.95)
        self.assertAlmostEqual(gender['Kvinde'][1], 1.40)

    def test_age_series_grouped_per_round(self):
        # Keyed off DRINKY_AGE_BRACKETS by position rather than by label, so
        # retuning the brackets doesn't break this: the fixture ages (30, 32,
        # 44, 45) only need to keep landing in the youngest and oldest ones.
        from .views import DRINKY_AGE_BRACKETS, _drinky_chart_data
        labels = [label for label, _ in DRINKY_AGE_BRACKETS]
        data = _drinky_chart_data()
        age = self.series(data, 'age_series')
        self.assertAlmostEqual(age[labels[0]][0], 1.10)
        self.assertAlmostEqual(age[labels[0]][1], 1.60)
        self.assertAlmostEqual(age[labels[-1]][0], 0.60)
        self.assertAlmostEqual(age[labels[-1]][1], 1.00)
        for label in labels[1:-1]:
            self.assertEqual(age[label], [None, None])

    def test_age_brackets_cover_every_allowed_age(self):
        # Anyone matching no bracket silently vanishes from the chart, so guard
        # the mistake that is easy to make when retuning them: leaving a gap.
        from .views import DRINKY_AGE_BRACKETS, _bracket_case
        round_obj = DrinkyRound.objects.create(number=99)
        for age in range(25, 76):
            player = make_player(nickname=f'Age{age}')
            player.age = age
            player.save()
            DrinkyReading.objects.create(round=round_obj, player=player, value='1.00')
        uncovered = (
            DrinkyReading.objects
            .filter(round=round_obj)
            .annotate(bracket=_bracket_case(DRINKY_AGE_BRACKETS))
            .filter(bracket__isnull=True)
            .values_list('player__age', flat=True)
        )
        self.assertEqual(sorted(uncovered), [])

    def test_group_of_one_is_suppressed(self):
        # Move p3 into a different bucket than p4, leaving each of them alone in
        # theirs; both buckets should then be dropped in both rounds.
        from .views import DRINKY_KIDS_BRACKETS, _drinky_chart_data
        self.p3.kids = 3
        self.p3.save()
        data = _drinky_chart_data()
        solo_a = self.bucket_of(self.p3, DRINKY_KIDS_BRACKETS)
        solo_b = self.bucket_of(self.p4, DRINKY_KIDS_BRACKETS)
        self.assertNotEqual(solo_a, solo_b)
        kids = self.series(data, 'kids_series')
        self.assertEqual(kids[solo_a], [None, None])
        self.assertEqual(kids[solo_b], [None, None])
        childless = self.bucket_of(self.p1, DRINKY_KIDS_BRACKETS)
        self.assertAlmostEqual(kids[childless][0], 1.10)
        self.assertAlmostEqual(kids[childless][1], 1.60)

    def test_three_and_four_kids_share_a_bucket(self):
        # The merge has to happen before the min-group-size filter: on their own
        # p3 (3 kids) and p4 (4 kids) are two groups of one and would both be
        # dropped, but pooled they are a group of two and get shown.
        from .views import DRINKY_KIDS_BRACKETS, _drinky_chart_data
        self.p3.kids = 3
        self.p3.save()
        self.p4.kids = 4
        self.p4.save()
        data = _drinky_chart_data()
        many_kids = self.bucket_of(self.p3, DRINKY_KIDS_BRACKETS)
        self.assertEqual(many_kids, self.bucket_of(self.p4, DRINKY_KIDS_BRACKETS))
        kids = self.series(data, 'kids_series')
        self.assertAlmostEqual(kids[many_kids][0], 0.60)
        self.assertAlmostEqual(kids[many_kids][1], 1.00)
        childless = self.bucket_of(self.p1, DRINKY_KIDS_BRACKETS)
        for label, _ in DRINKY_KIDS_BRACKETS:
            if label not in (many_kids, childless):
                self.assertEqual(kids[label], [None, None])


class SeedDrinkyCommandTests(TestCase):
    def test_creates_rounds_and_readings_within_bounds(self):
        call_command('seed_drinky', rounds=2, min_readings=5, max_readings=8, players=10)
        self.assertEqual(DrinkyRound.objects.count(), 2)
        for round_obj in DrinkyRound.objects.all():
            count = round_obj.readings.count()
            self.assertTrue(5 <= count <= 8, count)
        for reading in DrinkyReading.objects.all():
            self.assertTrue(Decimal('0.00') <= reading.value <= Decimal('2.99'))

    def test_tops_up_players_when_short(self):
        self.assertEqual(Player.objects.count(), 0)
        call_command('seed_drinky', rounds=1, min_readings=5, max_readings=5, players=5)
        self.assertEqual(Player.objects.count(), 5)

    def test_reuses_existing_players_with_demographics(self):
        for i in range(6):
            make_player(nickname=f'Real{i}')
        call_command('seed_drinky', rounds=1, min_readings=5, max_readings=5, players=5)
        # No fake guests needed: 6 real players already satisfy the pool size.
        self.assertEqual(Player.objects.filter(nickname__startswith='Testgæst').count(), 0)

    def test_appends_after_existing_rounds_without_number_clash(self):
        DrinkyRound.objects.create(number=1)
        call_command('seed_drinky', rounds=1, min_readings=5, max_readings=5, players=5)
        self.assertEqual(list(DrinkyRound.objects.order_by('number').values_list('number', flat=True)), [1, 2])
