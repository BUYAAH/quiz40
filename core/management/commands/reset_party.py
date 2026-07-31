from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import Answer, DrinkyReading, DrinkyRound, Player, Quiz


class Command(BaseCommand):
    help = (
        'Clears everything the guests generated (players, answers, drinky rounds '
        'and readings) and puts the quiz back to the waiting state. Questions, '
        'interlude images and the host login are kept. Run this on production '
        'once rehearsal is done, so the party starts from a clean slate and the '
        'test nicknames are free again.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Show what would be deleted and change nothing.',
        )
        parser.add_argument(
            '--yes', action='store_true',
            help='Skip the confirmation prompt.',
        )

    def handle(self, *args, **options):
        counts = {
            'players': Player.objects.count(),
            'quiz answers': Answer.objects.count(),
            'drinky rounds': DrinkyRound.objects.count(),
            'drinky readings': DrinkyReading.objects.count(),
        }
        quizzes = list(Quiz.objects.all())

        self.stdout.write('Will delete:')
        for label, count in counts.items():
            self.stdout.write(f'  {count:5} {label}')
        self.stdout.write('Will keep:')
        self.stdout.write(f'  {sum(quiz.questions.count() for quiz in quizzes):5} questions (and their interlude images)')
        for quiz in quizzes:
            self.stdout.write(f'  quiz "{quiz}" reset from state "{quiz.state}" to "waiting"')

        if options['dry_run']:
            self.stdout.write(self.style.WARNING('\nDry run: nothing changed.'))
            return

        if not options['yes']:
            self.stdout.write('')
            answer = input('Type RESET to confirm: ')
            if answer.strip() != 'RESET':
                self.stdout.write(self.style.ERROR('Aborted, nothing changed.'))
                return

        with transaction.atomic():
            # Answers and readings cascade from Player, but deleting them
            # explicitly keeps the reported numbers honest if a row ever
            # outlives its player.
            Answer.objects.all().delete()
            DrinkyReading.objects.all().delete()
            DrinkyRound.objects.all().delete()
            Player.objects.all().delete()
            for quiz in quizzes:
                quiz.state = Quiz.State.WAITING
                quiz.current_question = None
                quiz.save()

        self.stdout.write(self.style.SUCCESS('\nParty data cleared. Ready for guests.'))
