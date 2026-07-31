import uuid

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Quiz(models.Model):
    class State(models.TextChoices):
        WAITING = 'waiting', 'Waiting for players'
        INTERLUDE = 'interlude', 'Interlude (speech)'
        QUESTION_OPEN = 'open', 'Question open'
        REVEALED = 'revealed', 'Answer revealed'
        FINISHED = 'finished', 'Finished'

    name = models.CharField(max_length=100)
    state = models.CharField(
        max_length=10, choices=State.choices, default=State.WAITING
    )
    current_question = models.ForeignKey(
        'Question',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
    )
    class Meta:
        verbose_name_plural = 'quizzes'

    def __str__(self):
        return self.name


class Question(models.Model):
    class Option(models.TextChoices):
        A = 'a', 'A'
        B = 'b', 'B'
        C = 'c', 'C'
        D = 'd', 'D'

    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions')
    order = models.PositiveIntegerField()
    interlude_title = models.CharField(
        max_length=100,
        blank=True,
        help_text='Shown on the projector during the speech before this question.',
    )
    interlude_image = models.ImageField(
        upload_to='interludes/',
        blank=True,
        help_text='Shown on the projector below the interlude title.',
    )
    # Music is played manually from the projector laptop (local files), so the
    # app stores no audio: safer at party time than streaming from the server.
    option_a = models.CharField(max_length=100)
    option_b = models.CharField(max_length=100)
    option_c = models.CharField(max_length=100)
    option_d = models.CharField(max_length=100)
    correct_option = models.CharField(max_length=1, choices=Option.choices)
    correct_year = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ['order']
        constraints = [
            models.UniqueConstraint(fields=['quiz', 'order'], name='unique_question_order'),
        ]

    def __str__(self):
        return f'Q{self.order}: {self.correct_artist} ({self.correct_year})'

    @property
    def correct_artist(self):
        return getattr(self, f'option_{self.correct_option}')

    @property
    def options(self):
        """(value, label) pairs for the answer form."""
        return [
            (Question.Option.A, self.option_a),
            (Question.Option.B, self.option_b),
            (Question.Option.C, self.option_c),
            (Question.Option.D, self.option_d),
        ]


class Player(models.Model):
    """A registered party guest, shared by all features (quiz, later fun stuff).
    Created once on the welcome page; identified by a token cookie."""

    class Gender(models.TextChoices):
        MALE = 'm', 'Mand'
        FEMALE = 'f', 'Kvinde'

    class Relation(models.TextChoices):
        FAMILY = 'family', 'Familie'
        FRIEND = 'friend', 'Ven'
        # Stored value stays 'badminton' — only the label guests see changed.
        BADMINTON = 'badminton', 'Grindsted'

    nickname = models.CharField(max_length=30, unique=True)
    # Stored in a cookie so a refreshed/dropped phone rejoins with score intact.
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    # Demographics for the party stats feature; collected on /profil/ right
    # after signup and required (player_required redirects there until done),
    # but left optional at the model level since a Player can briefly exist
    # before that step completes.
    age = models.PositiveSmallIntegerField(null=True, blank=True)
    gender = models.CharField(max_length=1, choices=Gender.choices, blank=True)
    kids = models.PositiveSmallIntegerField(null=True, blank=True)
    relation = models.CharField(max_length=10, choices=Relation.choices, blank=True)

    def __str__(self):
        return self.nickname

    @property
    def demographics_done(self):
        return (
            self.age is not None
            and self.kids is not None
            and bool(self.gender)
            and bool(self.relation)
        )


class Answer(models.Model):
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='answers')
    chosen_option = models.CharField(max_length=1, choices=Question.Option.choices)
    guessed_year = models.PositiveSmallIntegerField()
    # Computed when the question is closed; 0 until then.
    artist_points = models.PositiveSmallIntegerField(default=0)
    year_points = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['player', 'question'], name='one_answer_per_question'),
        ]

    def __str__(self):
        return f'{self.player} / {self.question_id}'

    @property
    def total_points(self):
        return self.artist_points + self.year_points

    def compute_points(self):
        """Set points from the question's correct answer. Caller saves."""
        self.artist_points = 5 if self.chosen_option == self.question.correct_option else 0
        self.year_points = max(0, 5 - abs(self.guessed_year - self.question.correct_year))


class DrinkyRound(models.Model):
    """A single breathalyzer-reading window. Only one is ever open at once —
    opening a round closes any other open one (enforced by the host action)."""

    number = models.PositiveIntegerField(unique=True)
    title = models.CharField(
        max_length=50,
        blank=True,
        help_text="Optional label shown instead of the round number, e.g. a time like '15.00'.",
    )
    open = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['number']

    def __str__(self):
        return self.title or f'Runde {self.number}'


class DrinkyReading(models.Model):
    """A guest's one-shot promille entry for a round."""

    round = models.ForeignKey(DrinkyRound, on_delete=models.CASCADE, related_name='readings')
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='drinky_readings')
    value = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(2.99)],
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['round', 'player'], name='one_reading_per_round'),
        ]

    def __str__(self):
        return f'{self.player} / {self.round} / {self.value}'
