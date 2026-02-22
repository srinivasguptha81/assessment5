from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse

from attendance.models import Faculty, Student, Course
from .models import MakeUpSession, MakeUpAttendance, SchedulingSuggestion
from .ai_scheduler import get_scheduling_suggestions


# ─────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────

def get_faculty(user):
    try:
        return Faculty.objects.get(user=user)
    except Faculty.DoesNotExist:
        return None


def get_student(user):
    try:
        return Student.objects.get(user=user)
    except Student.DoesNotExist:
        return None


# ─────────────────────────────────────────
# FACULTY — Dashboard
# ─────────────────────────────────────────

@login_required
def faculty_dashboard(request):
    faculty = get_faculty(request.user)
    if not faculty:
        return redirect('attendance:dashboard')

    sessions = MakeUpSession.objects.filter(
        faculty=faculty
    ).select_related('course').order_by('-date')

    upcoming = sessions.filter(status__in=['SCHEDULED', 'ONGOING'])
    completed = sessions.filter(status='COMPLETED')

    # ✅ FIXED: removed is_active filter
    courses = Course.objects.filter(faculty=faculty)

    context = {
        'faculty': faculty,
        'upcoming': upcoming,
        'completed': completed,
        'courses': courses,
    }
    return render(request, 'makeup/faculty_dashboard.html', context)


# ─────────────────────────────────────────
# FACULTY — Schedule Session
# ─────────────────────────────────────────

@login_required
def schedule_session(request):
    faculty = get_faculty(request.user)
    if not faculty:
        return redirect('attendance:dashboard')

    # ✅ FIXED: removed is_active filter
    courses = Course.objects.filter(faculty=faculty)

    if request.method == 'POST':
        course_id = request.POST.get('course')
        date = request.POST.get('date')
        start_time = request.POST.get('start_time')
        end_time = request.POST.get('end_time')
        venue = request.POST.get('venue', '').strip()
        reason = request.POST.get('reason', 'OTHER')
        notes = request.POST.get('notes', '').strip()

        if not all([course_id, date, start_time, end_time, venue]):
            messages.error(request, 'Please fill all required fields.')
            return render(request, 'makeup/schedule_session.html', {'courses': courses})

        course = get_object_or_404(Course, id=course_id, faculty=faculty)

        session = MakeUpSession.objects.create(
            faculty=faculty,
            course=course,
            date=date,
            start_time=start_time,
            end_time=end_time,
            venue=venue,
            reason=reason,
            notes=notes,
        )

        # Generate AI suggestions safely
        try:
            suggestions = get_scheduling_suggestions(session)
            for s in suggestions:
                SchedulingSuggestion.objects.create(
                    session=session,
                    suggested_date=s['date'],
                    suggested_time=s['time'],
                    score=s['score'],
                    reason=s['reason'],
                )
        except Exception:
            pass  # Prevent crash if AI fails

        messages.success(
            request,
            f'Make-up class scheduled! Remedial Code: {session.remedial_code}'
        )
        return redirect('makeup:session_detail', session_id=session.id)

    context = {
        'courses': courses,
        'today': timezone.now().date()
    }
    return render(request, 'makeup/schedule_session.html', context)


# ─────────────────────────────────────────
# FACULTY — Session Detail
# ─────────────────────────────────────────

@login_required
def session_detail(request, session_id):
    faculty = get_faculty(request.user)
    session = get_object_or_404(MakeUpSession, id=session_id)

    if not request.user.is_staff and (not faculty or session.faculty != faculty):
        messages.error(request, 'Access denied.')
        return redirect('makeup:faculty_dashboard')

    attendances = session.attendances.select_related(
        'student__user'
    ).order_by('marked_at')

    suggestions = session.suggestions.order_by('-score')[:3]

    context = {
        'session': session,
        'attendances': attendances,
        'suggestions': suggestions,
    }
    return render(request, 'makeup/session_detail.html', context)


# ─────────────────────────────────────────
# FACULTY — Code Controls
# ─────────────────────────────────────────

@login_required
def activate_code(request, session_id):
    faculty = get_faculty(request.user)
    session = get_object_or_404(MakeUpSession, id=session_id, faculty=faculty)

    if request.method == 'POST':
        duration = int(request.POST.get('duration', 30))
        session.activate_code(duration_minutes=duration)
        messages.success(
            request,
            f'Code activated! Students have {duration} minutes to mark attendance.'
        )

    return redirect('makeup:session_detail', session_id=session.id)


@login_required
def deactivate_code(request, session_id):
    faculty = get_faculty(request.user)
    session = get_object_or_404(MakeUpSession, id=session_id, faculty=faculty)

    if request.method == 'POST':
        session.code_active = False
        session.status = 'COMPLETED'
        session.save()
        messages.success(request, 'Attendance closed. Session marked as completed.')

    return redirect('makeup:session_detail', session_id=session.id)


@login_required
def regenerate_code(request, session_id):
    faculty = get_faculty(request.user)
    session = get_object_or_404(MakeUpSession, id=session_id, faculty=faculty)

    if request.method == 'POST':
        session.regenerate_code()
        messages.success(
            request,
            f'New remedial code generated: {session.remedial_code}'
        )

    return redirect('makeup:session_detail', session_id=session.id)


# ─────────────────────────────────────────
# STUDENT — Dashboard
# ─────────────────────────────────────────

@login_required
def student_dashboard(request):
    student = get_student(request.user)
    if not student:
        return redirect('attendance:dashboard')

    # ✅ FIXED: removed is_active filter
    enrolled_courses = student.courses.all()

    sessions = MakeUpSession.objects.filter(
        course__in=enrolled_courses
    ).select_related('course', 'faculty__user').order_by('-date')

    marked_ids = set(
        MakeUpAttendance.objects.filter(
            student=student
        ).values_list('session_id', flat=True)
    )

    session_data = [
        {
            'session': s,
            'marked': s.id in marked_ids,
        }
        for s in sessions
    ]

    context = {
        'student': student,
        'session_data': session_data,
    }
    return render(request, 'makeup/student_dashboard.html', context)


# ─────────────────────────────────────────
# STUDENT — Mark Attendance
# ─────────────────────────────────────────

@login_required
def mark_attendance(request):
    student = get_student(request.user)
    if not student:
        return redirect('attendance:dashboard')

    if request.method == 'POST':
        code = request.POST.get('code', '').strip().upper()

        if not code or len(code) != 6:
            messages.error(request, 'Please enter a valid 6-character code.')
            return redirect('makeup:student_dashboard')

        try:
            session = MakeUpSession.objects.get(remedial_code=code)
        except MakeUpSession.DoesNotExist:
            messages.error(request, 'Invalid code. Please check and try again.')
            return redirect('makeup:student_dashboard')

        if not session.is_code_valid:
            if not session.code_active:
                messages.error(request, 'Code is not active yet.')
            else:
                messages.error(request, 'Code has expired.')
            return redirect('makeup:student_dashboard')

        if not student.courses.filter(id=session.course.id).exists():
            messages.error(request, 'You are not enrolled in this course.')
            return redirect('makeup:student_dashboard')

        if MakeUpAttendance.objects.filter(
                session=session,
                student=student
        ).exists():
            messages.warning(request, 'You have already marked attendance.')
            return redirect('makeup:student_dashboard')

        ip = request.META.get('REMOTE_ADDR')

        MakeUpAttendance.objects.create(
            session=session,
            student=student,
            status='PRESENT',
            code_used=code,
            ip_address=ip,
        )

        messages.success(
            request,
            f'Attendance marked for {session.course.code} on {session.date}!'
        )

    return redirect('makeup:student_dashboard')


# ─────────────────────────────────────────
# AJAX — Code Status API
# ─────────────────────────────────────────

def code_status_api(request, session_id):
    session = get_object_or_404(MakeUpSession, id=session_id)

    expires_in = 0
    if session.is_code_valid and session.code_expires_at:
        delta = session.code_expires_at - timezone.now()
        expires_in = max(0, int(delta.total_seconds()))

    return JsonResponse({
        'active': session.is_code_valid,
        'expires_in': expires_in,
        'status': session.status,
    })