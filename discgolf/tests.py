from django.test import TestCase

from .models import Card, Course, Hole, Player, Score


class DiscgolfFlowTests(TestCase):
    def setUp(self):
        self.course = Course.objects.create(name='Rethrow Park')
        for n in range(1, 5):
            Hole.objects.create(course=self.course, number=n, par=3,
                                description=f'Beskrivelse af hul {n}')

    def test_front_page(self):
        r = self.client.get('/')
        self.assertContains(r, 'Start gruppe')

    def test_card_code_is_four_digits_and_not_pk(self):
        self.client.post('/gruppe/start/')
        card = Card.objects.get()
        self.assertRegex(card.code, r'^\d{4}$')
        # The pk-based URL must not work
        r = self.client.get(f'/gruppe/{card.pk}/')
        if str(card.pk) != card.code:
            self.assertEqual(r.status_code, 404)

    def test_full_round(self):
        r = self.client.post('/gruppe/start/')
        card = Card.objects.get()
        setup_url = f'/gruppe/{card.code}/'
        self.assertRedirects(r, setup_url)

        for name in ['Anna', 'Bo', 'Carla']:
            r = self.client.post(setup_url, {'name': name})
            self.assertRedirects(r, setup_url)

        # Duplicate name (case-insensitive) is rejected
        r = self.client.post(setup_url, {'name': 'anna'})
        self.assertContains(r, 'allerede')
        self.assertEqual(card.players.count(), 3)

        # Remove a player
        removed = card.players.last()
        r = self.client.post(f'/gruppe/{card.code}/spiller/{removed.pk}/slet/')
        self.assertRedirects(r, setup_url)
        self.assertEqual(card.players.count(), 2)
        self.client.post(setup_url, {'name': 'Carla'})

        players = list(card.players.all())
        for n in range(1, 5):
            url = f'/gruppe/{card.code}/hul/{n}/'
            r = self.client.get(url)
            self.assertContains(r, f'Hul {n}')
            self.assertContains(r, f'Beskrivelse af hul {n}')
            data = {f'strokes_{p.pk}': 3 + i for i, p in enumerate(players)}
            r = self.client.post(url, data)
            if n < 4:
                self.assertRedirects(r, f'/gruppe/{card.code}/hul/{n + 1}/')
            else:
                self.assertRedirects(r, f'/gruppe/{card.code}/resultat/')
        self.assertEqual(Score.objects.count(), 12)

        # Going back and editing a hole updates instead of duplicating
        r = self.client.post(
            f'/gruppe/{card.code}/hul/2/',
            {f'strokes_{p.pk}': 2 for p in players},
        )
        self.assertRedirects(r, f'/gruppe/{card.code}/hul/3/')
        self.assertEqual(Score.objects.count(), 12)
        self.assertEqual(
            Score.objects.get(player=players[0], hole__number=2).strokes, 2)

        # Results page: totals and leaderboard
        r = self.client.get(f'/gruppe/{card.code}/resultat/')
        self.assertContains(r, 'Dagens stilling')
        self.assertContains(r, 'Anna')

        r = self.client.get('/stilling/')
        self.assertContains(r, 'Anna')

    def test_invalid_strokes_rerenders_with_error(self):
        card = Card.objects.create(course=self.course)
        player = Player.objects.create(card=card, name='Anna')
        r = self.client.post(f'/gruppe/{card.code}/hul/1/',
                             {f'strokes_{player.pk}': 'abc'})
        self.assertContains(r, 'kast')
        self.assertEqual(Score.objects.count(), 0)

    def test_hole_without_players_redirects_to_setup(self):
        card = Card.objects.create(course=self.course)
        r = self.client.get(f'/gruppe/{card.code}/hul/1/')
        self.assertRedirects(r, f'/gruppe/{card.code}/')

    def test_resume_without_session_goes_to_front(self):
        r = self.client.get('/runde/')
        self.assertRedirects(r, '/')

    def test_resume_follows_round_state(self):
        self.client.post('/gruppe/start/')
        card = Card.objects.get()

        # No players yet: resume lands on setup
        r = self.client.get('/runde/')
        self.assertRedirects(r, f'/gruppe/{card.code}/')

        self.client.post(f'/gruppe/{card.code}/', {'name': 'Anna'})
        self.client.post(f'/gruppe/{card.code}/', {'name': 'Bo'})
        players = list(card.players.all())

        # Round started, nothing scored: resume lands on hole 1
        r = self.client.get('/runde/')
        self.assertRedirects(r, f'/gruppe/{card.code}/hul/1/')

        # Holes 1-2 scored: resume lands on hole 3 (e.g. after visiting Stilling)
        for n in [1, 2]:
            self.client.post(f'/gruppe/{card.code}/hul/{n}/',
                             {f'strokes_{p.pk}': 3 for p in players})
        self.client.get('/stilling/')
        r = self.client.get('/runde/')
        self.assertRedirects(r, f'/gruppe/{card.code}/hul/3/')

        # All holes scored: resume lands on results
        for n in [3, 4]:
            self.client.post(f'/gruppe/{card.code}/hul/{n}/',
                             {f'strokes_{p.pk}': 3 for p in players})
        r = self.client.get('/runde/')
        self.assertRedirects(r, f'/gruppe/{card.code}/resultat/')

    def test_navbar_resume_link_shown_after_joining_card(self):
        r = self.client.get('/')
        self.assertNotContains(r, 'Jeres runde')
        self.client.post('/gruppe/start/')
        r = self.client.get('/stilling/')
        self.assertContains(r, 'Jeres runde')
        r = self.client.get('/')
        self.assertContains(r, 'Fortsæt jeres runde')

    def test_visiting_card_url_adopts_it_into_session(self):
        card = Card.objects.create(course=self.course)
        self.client.get(f'/gruppe/{card.code}/')
        r = self.client.get('/runde/')
        self.assertRedirects(r, f'/gruppe/{card.code}/')

    def test_leaderboard_ranks_and_in_progress(self):
        card = Card.objects.create(course=self.course)
        done1 = Player.objects.create(card=card, name='Anna')
        done2 = Player.objects.create(card=card, name='Bo')
        partial = Player.objects.create(card=card, name='Carla')
        for hole in self.course.holes.all():
            Score.objects.create(player=done1, hole=hole, strokes=3)
            Score.objects.create(player=done2, hole=hole, strokes=3)
        Score.objects.create(player=partial, hole=self.course.holes.first(), strokes=4)

        r = self.client.get('/stilling/')
        # Tied players share placement 1; Carla is listed as still playing
        self.assertContains(r, 'Anna')
        self.assertContains(r, 'Bo')
        self.assertContains(r, 'Stadig i gang')
        self.assertContains(r, 'Carla')
        sections = r.context['sections']
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0]['label'], 'Voksen')
        self.assertEqual([row['rank'] for row in sections[0]['rows']], [1, 1])
        self.assertEqual(sections[0]['rows'][0]['to_par'], 0)

    def test_divisions_get_separate_leaderboards(self):
        card = Card.objects.create(course=self.course)
        adult = Player.objects.create(card=card, name='Anna')
        child = Player.objects.create(
            card=card, name='Emil', division=Player.Division.CHILD)
        for hole in self.course.holes.all():
            Score.objects.create(player=adult, hole=hole, strokes=3)
            Score.objects.create(player=child, hole=hole, strokes=6)

        r = self.client.get('/stilling/')
        sections = r.context['sections']
        self.assertEqual([s['label'] for s in sections], ['Voksen', 'Barn'])
        # Each division is ranked on its own: both players place 1st
        self.assertEqual(sections[0]['rows'][0]['rank'], 1)
        self.assertEqual(sections[0]['rows'][0]['player'], adult)
        self.assertEqual(sections[1]['rows'][0]['rank'], 1)
        self.assertEqual(sections[1]['rows'][0]['player'], child)

    def test_setup_adds_player_with_division(self):
        self.client.post('/gruppe/start/')
        card = Card.objects.get()
        self.client.post(f'/gruppe/{card.code}/',
                         {'name': 'Emil', 'division': 'child'})
        self.assertEqual(card.players.get().division, Player.Division.CHILD)
        # Missing/invalid division falls back to Voksen
        self.client.post(f'/gruppe/{card.code}/', {'name': 'Anna'})
        self.assertEqual(
            card.players.get(name='Anna').division, Player.Division.ADULT)
        # The child gets a badge on the group page
        r = self.client.get(f'/gruppe/{card.code}/')
        self.assertContains(r, 'Barn')

    def test_party_home_moved_to_fest(self):
        r = self.client.get('/fest/')
        # player_required redirects unregistered visitors to the welcome page
        self.assertEqual(r.status_code, 302)
        self.assertIn('/velkommen/', r.url)

    def test_front_page_without_course(self):
        Course.objects.all().delete()
        r = self.client.get('/')
        self.assertContains(r, 'ikke sat op')
