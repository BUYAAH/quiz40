import random

from django.core.management.base import BaseCommand

from core.models import Answer, Player, Question, Quiz


class Command(BaseCommand):
    help = (
        'If the active quiz has a question open, submits a random answer for '
        'every player who hasn\'t answered it yet. For trying out the host/'
        'projector panels without gathering real guests.'
    )

    def handle(self, *args, **options):
        quiz = Quiz.objects.order_by('-id').first()
        if quiz is None:
            self.stderr.write(self.style.ERROR('No quiz exists yet.'))
            return
        if quiz.state != Quiz.State.QUESTION_OPEN or quiz.current_question is None:
            self.stdout.write('No question is currently open.')
            return

        question = quiz.current_question
        already_answered = set(
            Answer.objects.filter(question=question).values_list('player_id', flat=True)
        )
        players = Player.objects.exclude(id__in=already_answered)

        answers = [
            Answer(
                player=player,
                question=question,
                chosen_option=random.choice(Question.Option.values),
                guessed_year=random.randint(1950, 2025),
            )
            for player in players
        ]
        Answer.objects.bulk_create(answers)
        self.stdout.write(self.style.SUCCESS(
            f'Answered "{question}" randomly for {len(answers)} player(s).'
        ))
