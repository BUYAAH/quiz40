import random

from django.db import models


def new_card_code():
    """Random 4-digit code so card URLs can't be guessed by counting up."""
    for _ in range(100):
        code = f'{random.randint(0, 9999):04d}'
        if not Card.objects.filter(code=code).exists():
            return code
    raise RuntimeError('No free card codes left')


class Course(models.Model):
    """A disc golf course; the event uses one course with a handful of holes."""

    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

    @property
    def total_par(self):
        return sum(hole.par for hole in self.holes.all())


class Hole(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='holes')
    number = models.PositiveIntegerField()
    par = models.IntegerField(default=3)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='discgolf/', blank=True)

    class Meta:
        ordering = ['number']
        constraints = [
            models.UniqueConstraint(fields=['course', 'number'], name='unique_hole_number'),
        ]

    def __str__(self):
        return f'Hul {self.number} (par {self.par})'


class Card(models.Model):
    """A group's scorecard for one round. Created by whoever pressed
    'Start gruppe'; identified in URLs by a random 4-digit code (not the
    sequential pk, which would let groups guess each other's cards). The
    code is also kept in the creator's session so the navbar can link back
    to the current round."""

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='cards')
    code = models.CharField(max_length=4, unique=True, default=new_card_code)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Gruppe {self.code}'


class Player(models.Model):
    """A player on one card. Separate from core.Player — disc golf players
    just type a name, no site-wide registration."""

    class Division(models.TextChoices):
        ADULT = 'adult', 'Voksen'
        CHILD = 'child', 'Barn'

    card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name='players')
    name = models.CharField(max_length=30)
    division = models.CharField(
        max_length=5, choices=Division.choices, default=Division.ADULT
    )

    class Meta:
        ordering = ['id']

    def __str__(self):
        return self.name


class Score(models.Model):
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='scores')
    hole = models.ForeignKey(Hole, on_delete=models.CASCADE, related_name='scores')
    strokes = models.PositiveSmallIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['player', 'hole'], name='one_score_per_hole'),
        ]

    def __str__(self):
        return f'{self.player} / {self.hole} / {self.strokes}'
