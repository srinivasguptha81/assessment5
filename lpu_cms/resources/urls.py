from django.urls import path
from . import views

app_name = 'resources'

urlpatterns = [
    path('',                              views.dashboard,          name='dashboard'),
    path('block/<int:block_id>/',         views.block_detail,       name='block_detail'),
    path('room/<int:room_id>/',           views.classroom_detail,   name='classroom_detail'),
    path('faculty-workload/',             views.faculty_workload,   name='faculty_workload'),
    path('courses/',                      views.course_list,        name='course_list'),
    path('courses/<int:course_id>/',      views.course_detail,      name='course_detail'),
    path('my-timetable/',                 views.my_timetable,       name='my_timetable'),
    path('utilization/',                  views.utilization_report, name='utilization_report'),
]