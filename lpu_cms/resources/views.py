from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Avg, Q
from django.utils import timezone
from collections import defaultdict

from attendance.models import Faculty, Student, Department
from .models import Block, Classroom, Course, Enrollment, WorkloadRecord


# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────

# Workload thresholds (hours/week)
OVERLOAD_THRESHOLD  = 20
UNDERLOAD_THRESHOLD = 6


def calculate_faculty_workload(faculty):
    """
    Calculates workload for a faculty member based on their active courses.
    Updates or creates a WorkloadRecord.

    Workload = sum of hours_per_week across all active courses taught.
    Status:
      > 20 hrs/week → Overloaded
      < 6  hrs/week → Underloaded
      else          → Normal
    """
    courses = Course.objects.filter(faculty=faculty, is_active=True)

    total_courses    = courses.count()
    total_hours_week = courses.aggregate(Sum('hours_per_week'))['hours_per_week__sum'] or 0
    total_students   = sum(c.enrolled_count for c in courses)

    if total_hours_week > OVERLOAD_THRESHOLD:
        status = 'OVERLOADED'
    elif total_hours_week < UNDERLOAD_THRESHOLD:
        status = 'UNDERLOAD'
    else:
        status = 'NORMAL'

    record, _ = WorkloadRecord.objects.update_or_create(
        faculty=faculty,
        semester=1,
        academic_year='2024-25',
        defaults={
            'total_courses':    total_courses,
            'total_hours_week': total_hours_week,
            'total_students':   total_students,
            'status':           status,
        }
    )
    return record


# ─────────────────────────────────────────
# MAIN DASHBOARD
# ─────────────────────────────────────────

@login_required
def dashboard(request):
    """
    Campus-wide overview:
    - Block utilization
    - Total capacity vs enrolled
    - Overloaded faculty count
    - Department-wise enrollment
    """
    blocks      = Block.objects.prefetch_related('classrooms').all()
    total_cap   = sum(b.total_capacity for b in blocks)
    total_enr   = Enrollment.objects.filter(is_active=True).values('student').distinct().count()
    campus_util = round((total_enr / total_cap * 100), 1) if total_cap else 0

    # Recalculate workload for all faculty
    all_faculty = Faculty.objects.all()
    workloads   = [calculate_faculty_workload(f) for f in all_faculty]

    overloaded  = sum(1 for w in workloads if w.status == 'OVERLOADED')
    underloaded = sum(1 for w in workloads if w.status == 'UNDERLOAD')
    normal      = sum(1 for w in workloads if w.status == 'NORMAL')

    # Department enrollment stats
    departments = Department.objects.all()
    dept_data   = []
    for dept in departments:
        enr = Enrollment.objects.filter(
            course__department=dept, is_active=True
        ).values('student').distinct().count()
        courses = Course.objects.filter(department=dept, is_active=True).count()
        dept_data.append({
            'dept':    dept,
            'enrolled': enr,
            'courses': courses,
        })

    # Block utilization for chart
    block_labels = [b.code for b in blocks]
    block_utils  = [b.utilization_percent for b in blocks]

    import json
    context = {
        'blocks':       blocks,
        'total_cap':    total_cap,
        'total_enr':    total_enr,
        'campus_util':  campus_util,
        'overloaded':   overloaded,
        'underloaded':  underloaded,
        'normal':       normal,
        'total_faculty': all_faculty.count(),
        'dept_data':    dept_data,
        'block_labels': json.dumps(block_labels),
        'block_utils':  json.dumps(block_utils),
    }
    return render(request, 'resources/dashboard.html', context)


# ─────────────────────────────────────────
# BLOCK & CLASSROOM DETAIL
# ─────────────────────────────────────────

@login_required
def block_detail(request, block_id):
    block      = get_object_or_404(Block, id=block_id)
    classrooms = block.classrooms.filter(is_active=True).order_by('room_number')

    context = {
        'block':      block,
        'classrooms': classrooms,
    }
    return render(request, 'resources/block_detail.html', context)


@login_required
def classroom_detail(request, room_id):
    room    = get_object_or_404(Classroom, id=room_id)
    courses = Course.objects.filter(classroom=room, is_active=True).select_related('faculty')

    context = {
        'room':    room,
        'courses': courses,
    }
    return render(request, 'resources/classroom_detail.html', context)


# ─────────────────────────────────────────
# FACULTY WORKLOAD
# ─────────────────────────────────────────

@login_required
def faculty_workload(request):
    """
    Shows workload distribution for all faculty.
    Highlights overloaded and underloaded members.
    Used for administrative rebalancing.
    """
    all_faculty = Faculty.objects.select_related('user', 'department').all()
    workload_data = []

    for f in all_faculty:
        record  = calculate_faculty_workload(f)
        courses = Course.objects.filter(faculty=f, is_active=True)
        workload_data.append({
            'faculty':  f,
            'record':   record,
            'courses':  courses,
        })

    # Sort: overloaded first, then normal, then underloaded
    order = {'OVERLOADED': 0, 'NORMAL': 1, 'UNDERLOAD': 2}
    workload_data.sort(key=lambda x: order.get(x['record'].status, 1))

    # Chart data — hours per week per faculty
    import json
    chart_labels = [d['faculty'].user.get_full_name() or d['faculty'].faculty_id for d in workload_data]
    chart_data   = [d['record'].total_hours_week for d in workload_data]
    chart_colors = [
        '#b34a2f' if d['record'].status == 'OVERLOADED'
        else '#2d5016' if d['record'].status == 'UNDERLOAD'
        else '#c9a84c'
        for d in workload_data
    ]

    context = {
        'workload_data':       workload_data,
        'overload_threshold':  OVERLOAD_THRESHOLD,
        'underload_threshold': UNDERLOAD_THRESHOLD,
        'chart_labels':        json.dumps(chart_labels),
        'chart_data':          json.dumps(chart_data),
        'chart_colors':        json.dumps(chart_colors),
    }
    return render(request, 'resources/faculty_workload.html', context)


# ─────────────────────────────────────────
# COURSE LIST & DETAIL
# ─────────────────────────────────────────

@login_required
def course_list(request):
    dept_id = request.GET.get('dept')
    sem     = request.GET.get('sem')

    courses = Course.objects.filter(is_active=True).select_related(
        'faculty__user', 'classroom__block', 'department'
    )
    if dept_id:
        courses = courses.filter(department_id=dept_id)
    if sem:
        courses = courses.filter(semester=sem)

    departments = Department.objects.all()
    context = {
        'courses':     courses,
        'departments': departments,
        'selected_dept': dept_id,
        'selected_sem':  sem,
    }
    return render(request, 'resources/course_list.html', context)


@login_required
def course_detail(request, course_id):
    course      = get_object_or_404(Course, id=course_id)
    enrollments = Enrollment.objects.filter(
        course=course, is_active=True
    ).select_related('student__user')

    context = {
        'course':      course,
        'enrollments': enrollments,
    }
    return render(request, 'resources/course_detail.html', context)


# ─────────────────────────────────────────
# STUDENT TIMETABLE
# ─────────────────────────────────────────

@login_required
def my_timetable(request):
    try:
        student = Student.objects.get(user=request.user)
    except Student.DoesNotExist:
        return redirect('attendance:dashboard')

    enrollments = Enrollment.objects.filter(
        student=student, is_active=True
    ).select_related('course__faculty__user', 'course__classroom__block')

    context = {
        'student':     student,
        'enrollments': enrollments,
    }
    return render(request, 'resources/my_timetable.html', context)


# ─────────────────────────────────────────
# CAPACITY UTILIZATION REPORT
# ─────────────────────────────────────────

@login_required
def utilization_report(request):
    """
    Detailed utilization report for all classrooms.
    Shows capacity vs actual enrollment with status flags.
    """
    classrooms = Classroom.objects.filter(
        is_active=True
    ).select_related('block').prefetch_related('courses')

    # Categorise
    overcrowded = [c for c in classrooms if c.utilization_percent >= 90]
    high        = [c for c in classrooms if 70 <= c.utilization_percent < 90]
    moderate    = [c for c in classrooms if 40 <= c.utilization_percent < 70]
    low         = [c for c in classrooms if c.utilization_percent < 40]

    total_cap = sum(c.capacity for c in classrooms)
    total_enr = sum(c.current_enrollment for c in classrooms)
    overall   = round((total_enr / total_cap * 100), 1) if total_cap else 0

    context = {
        'classrooms':  classrooms,
        'overcrowded': overcrowded,
        'high':        high,
        'moderate':    moderate,
        'low':         low,
        'total_cap':   total_cap,
        'total_enr':   total_enr,
        'overall':     overall,
    }
    return render(request, 'resources/utilization_report.html', context)