import random
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Max

from core.models import DrinkyReading, DrinkyRound, Player

FAKE_NICKNAME_PREFIX = 'Testgæst'


class Command(BaseCommand):
    help = (
        'Seeds Drinky with a few rounds of random readings, for trying out the '
        '/drinky/projektor/ charts without a real party. Creates fake players '
        '(with random demographics) if there aren\'t enough real ones yet.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--rounds', type=int, default=3)
        parser.add_argument('--min-readings', type=int, default=25)
        parser.add_argument('--max-readings', type=int, default=35)
        parser.add_argument(
            '--players', type=int, default=35,
            help='Minimum player pool size; fake guests top it up if short.',
        )

    def handle(self, *args, **options):
        num_rounds = options['rounds']
        min_readings = options['min_readings']
        max_readings = options['max_readings']
        pool_size = options['players']

        players = list(Player.objects.filter(
            age__isnull=False, kids__isnull=False,
        ).exclude(gender='').exclude(relation=''))
        players += self._top_up_players(pool_size - len(players))

        if len(players) < min_readings:
            self.stderr.write(self.style.ERROR(
                f'Only {len(players)} players with demographics available, '
                f'need at least {min_readings}. Raise --players or lower --min-readings.'
            ))
            return

        next_number = (DrinkyRound.objects.aggregate(Max('number'))['number__max'] or 0) + 1
        for i in range(num_rounds):
            round_obj = DrinkyRound.objects.create(number=next_number + i)
            count = random.randint(min_readings, min(max_readings, len(players)))
            for player in random.sample(players, count):
                DrinkyReading.objects.create(
                    round=round_obj,
                    player=player,
                    value=self._random_value(i, num_rounds),
                )
            self.stdout.write(self.style.SUCCESS(f'{round_obj}: {count} readings'))

    def _top_up_players(self, missing):
        if missing <= 0:
            return []
        created = []
        existing = Player.objects.filter(nickname__startswith=FAKE_NICKNAME_PREFIX).count()
        for i in range(existing + 1, existing + 1 + missing):
            created.append(Player.objects.create(
                nickname=f'{FAKE_NICKNAME_PREFIX}{i}',
                age=random.randint(25, 75),
                gender=random.choice(Player.Gender.values),
                kids=random.randint(0, 4),
                relation=random.choice(Player.Relation.values),
            ))
        return created

    def _random_value(self, round_index, total_rounds):
        """Readings trend upward across rounds, like a real party would."""
        progress = round_index / max(total_rounds - 1, 1)
        low = 0.00 + progress * 0.90
        high = min(1.00 + progress * 1.80, 2.99)
        return Decimal(str(round(random.uniform(low, high), 2)))
