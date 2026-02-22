from django.urls import path
from . import views

app_name = 'makeup'

urlpatterns = [
    # Faculty
    path('',                                  views.faculty_dashboard, name='faculty_dashboard'),
    path('schedule/',                         views.schedule_session,  name='schedule_session'),
    path('session/<int:session_id>/',         views.session_detail,    name='session_detail'),
    path('session/<int:session_id>/activate/',   views.activate_code,  name='activate_code'),
    path('session/<int:session_id>/deactivate/', views.deactivate_code,name='deactivate_code'),
    path('session/<int:session_id>/regenerate/', views.regenerate_code,name='regenerate_code'),

    # Student
    path('student/',       views.student_dashboard, name='student_dashboard'),
    path('mark/',          views.mark_attendance,   name='mark_attendance'),

    # API
    path('api/status/<int:session_id>/', views.code_status_api, name='code_status_api'),
]