from django.contrib import admin
from .models import Block, Classroom, Course, Enrollment, WorkloadRecord

@admin.register(Classroom)
class ClassroomAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'capacity', 'room_type', 'has_projector', 'is_active']
    list_filter  = ['block', 'room_type']

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display  = ['code', 'name', 'faculty', 'classroom', 'semester', 'enrolled_count']
    list_filter   = ['semester', 'department']
    search_fields = ['code', 'name']

admin.site.register(Block)
admin.site.register(Enrollment)
admin.site.register(WorkloadRecord)