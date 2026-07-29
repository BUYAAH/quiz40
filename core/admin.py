from django.contrib import admin

from .models import Answer, DrinkyReading, DrinkyRound, Player, Question, Quiz


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ('name', 'state', 'current_question')


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('order', 'correct_artist', 'correct_year', 'quiz')
    list_filter = ('quiz',)
    ordering = ('quiz', 'order')
    fieldsets = (
        (None, {'fields': ('quiz', 'order')}),
        ('Interlude', {'fields': ('interlude_title', 'interlude_image')}),
        ('Song', {'fields': ('correct_year',)}),
        ('Artist options', {
            'fields': ('option_a', 'option_b', 'option_c', 'option_d', 'correct_option'),
        }),
    )


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ('nickname', 'age', 'gender', 'kids', 'relation', 'created_at')
    list_filter = ('gender', 'relation')
    search_fields = ('nickname',)


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ('player', 'question', 'chosen_option', 'guessed_year',
                    'artist_points', 'year_points')
    list_filter = ('question__quiz', 'question')


@admin.register(DrinkyRound)
class DrinkyRoundAdmin(admin.ModelAdmin):
    list_display = ('number', 'title', 'open', 'created_at')


@admin.register(DrinkyReading)
class DrinkyReadingAdmin(admin.ModelAdmin):
    list_display = ('player', 'round', 'value', 'created_at')
    list_filter = ('round',)
