from django.contrib import admin

from .models import Card, Course, Hole, Player, Score


class HoleInline(admin.StackedInline):
    model = Hole
    extra = 0


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('name',)
    inlines = [HoleInline]


@admin.register(Hole)
class HoleAdmin(admin.ModelAdmin):
    list_display = ('number', 'par', 'course')
    list_filter = ('course',)
    ordering = ('course', 'number')


class PlayerInline(admin.TabularInline):
    model = Player
    extra = 0


@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
    list_display = ('code', 'course', 'created_at')
    inlines = [PlayerInline]


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ('name', 'division', 'card')
    list_filter = ('division', 'card')


@admin.register(Score)
class ScoreAdmin(admin.ModelAdmin):
    list_display = ('player', 'hole', 'strokes')
    list_filter = ('hole',)
