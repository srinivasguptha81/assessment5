from django.db import models
from django.utils import timezone
from attendance.models import Faculty, Student, Course
import random
import string


def generate_remedial_code():
    """
    Generates a unique 6-character alphanumeric code.
    e.g. 'A3X7K2'
    Used by students to mark attendance for make-up classes.
    """
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


# ─────────────────────────────────────────
# MAKE-UP CLASS SESSION
# Faculty creates this to schedule a make-up
# ─────────────────────────────────────────
class MakeUpSession(models.Model):

    STATUS_CHOICES = [
        ('SCHEDULED', 'Scheduled'),
        ('ONGOING',   'Ongoing'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    ]

    REASON_CHOICES = [
        ('HOLIDAY',  'Previous Class Missed — Holiday'),
        ('SICK',     'Faculty Was Sick'),
        ('EVENT',    'College Event'),
        ('EXTRA',    'Extra Coverage Needed'),
        ('OTHER',    'Other'),
    ]

    faculty        = models.ForeignKey(Faculty, on_delete=models.CASCADE, related_name='makeup_sessions')
    course         = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='makeup_sessions')
    date           = models.DateField()
    start_time     = models.TimeField()
    end_time       = models.TimeField()
    venue          = models.CharField(max_length=100, help_text='e.g. Block 32 Room 101')
    reason         = models.CharField(max_length=10, choices=REASON_CHOICES, default='OTHER')
    notes          = models.TextField(blank=True)

    # The unique code students use to mark attendance
    remedial_code  = models.CharField(max_length=6, unique=True, default=generate_remedial_code)

    # Code is only active during the class window
    code_active    = models.BooleanField(default=False)
    code_activated_at = models.DateTimeField(null=True, blank=True)
    code_expires_at   = models.DateTimeField(null=True, blank=True)

    status         = models.CharField(max_length=10, choices=STATUS_CHOICES, default='SCHEDULED')
    created_at     = models.DateTimeField(auto_now_add=True)

    # AI scheduling score (0-100, higher = better slot)
    ai_score       = models.IntegerField(default=0)

    class Meta:
        ordering = ['date', 'start_time']

    def __str__(self):
        return f"{self.course.code} Make-up | {self.date} {self.start_time} | Code: {self.remedial_code}"

    @property
    def is_upcoming(self):
        return self.date >= timezone.now().date() and self.status == 'SCHEDULED'

    @property
    def is_code_valid(self):
        """Code is valid only when faculty has activated it and it hasn't expired."""
        if not self.code_active:
            return False
        now = timezone.now()
        if self.code_expires_at and now > self.code_expires_at:
            return False
        return True

    @property
    def attendance_count(self):
        return self.attendances.filter(status='PRESENT').count()

    @property
    def total_enrolled(self):
        return self.course.students.count()

    @property
    def attendance_percent(self):
        total = self.total_enrolled
        if total == 0:
            return 0
        return round((self.attendance_count / total) * 100, 1)

    def activate_code(self, duration_minutes=30):
        """Faculty activates the code — students can now mark attendance."""
        self.code_active = True
        self.code_activated_at = timezone.now()
        self.code_expires_at   = timezone.now() + timezone.timedelta(minutes=duration_minutes)
        self.status = 'ONGOING'
        self.save()

    def regenerate_code(self):
        """Generate a fresh code — useful if code was leaked."""
        self.remedial_code = generate_remedial_code()
        self.save()


# ─────────────────────────────────────────
# MAKE-UP ATTENDANCE
# Student marks attendance using remedial code
# ─────────────────────────────────────────
class MakeUpAttendance(models.Model):

    STATUS_CHOICES = [
        ('PRESENT', 'Present'),
        ('ABSENT',  'Absent'),
    ]

    session    = models.ForeignKey(MakeUpSession, on_delete=models.CASCADE, related_name='attendances')
    student    = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='makeup_attendances')
    status     = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PRESENT')
    marked_at  = models.DateTimeField(auto_now_add=True)
    code_used  = models.CharField(max_length=6)  # snapshot of code at time of marking
    ip_address = models.GenericIPAddressField(null=True, blank=True)  # basic fraud prevention

    class Meta:
        unique_together = ('session', 'student')  # one entry per student per session

    def __str__(self):
        return f"{self.student} → {self.session.course.code} Make-up | {self.status}"


# ─────────────────────────────────────────
# AI SCHEDULING SUGGESTION
# Stores AI-generated slot recommendations
# ─────────────────────────────────────────
class SchedulingSuggestion(models.Model):

    session       = models.ForeignKey(MakeUpSession, on_delete=models.CASCADE, related_name='suggestions')
    suggested_date = models.DateField()
    suggested_time = models.TimeField()
    score          = models.IntegerField(default=0, help_text='0-100, higher = better')
    reason         = models.TextField()  # human-readable explanation
    is_accepted    = models.BooleanField(default=False)
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-score']

    def __str__(self):
        return f"Suggestion for {self.session} → {self.suggested_date} {self.suggested_time} (score {self.score})"