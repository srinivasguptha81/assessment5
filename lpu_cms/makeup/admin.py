from django.contrib import admin
from .models import MakeUpSession, MakeUpAttendance, SchedulingSuggestion

class MakeUpAttendanceInline(admin.TabularInline):
    model  = MakeUpAttendance
    extra  = 0
    fields = ['student', 'status', 'marked_at', 'code_used']
    readonly_fields = ['marked_at', 'code_used']

@admin.register(MakeUpSession)
class MakeUpSessionAdmin(admin.ModelAdmin):
    list_display  = ['course', 'faculty', 'date', 'start_time', 'remedial_code', 'code_active', 'status', 'attendance_count']
    list_filter   = ['status', 'code_active', 'reason']
    search_fields = ['course__code', 'remedial_code']
    readonly_fields = ['remedial_code', 'code_activated_at', 'code_expires_at']
    inlines = [MakeUpAttendanceInline]

admin.site.register(MakeUpAttendance)
admin.site.register(SchedulingSuggestion)