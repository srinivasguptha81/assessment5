from django.db import models
from django.utils import timezone
from attendance.models import Faculty, Student, Department


# ─────────────────────────────────────────
# CAMPUS BLOCK
# Physical building on campus e.g. Block 32
# ─────────────────────────────────────────
class Block(models.Model):
    name         = models.CharField(max_length=100)
    code         = models.CharField(max_length=10, unique=True)
    total_floors = models.IntegerField(default=1)
    description  = models.TextField(blank=True)

    def __str__(self):
        return f"{self.code} — {self.name}"

    @property
    def total_classrooms(self):
        return self.classrooms.count()

    @property
    def total_capacity(self):
        return self.classrooms.aggregate(
            total=models.Sum('capacity')
        )['total'] or 0

    @property
    def utilization_percent(self):
        """
        Average utilization across all classrooms in this block.
        Based on current enrollments vs total capacity.
        """
        classrooms = self.classrooms.all()
        if not classrooms:
            return 0
        total = sum(c.utilization_percent for c in classrooms)
        return round(total / classrooms.count(), 1)


# ─────────────────────────────────────────
# CLASSROOM
# Individual room inside a block
# ─────────────────────────────────────────
class Classroom(models.Model):

    ROOM_TYPES = [
        ('LECTURE',  'Lecture Hall'),
        ('LAB',      'Computer Lab'),
        ('SEMINAR',  'Seminar Room'),
        ('TUTORIAL', 'Tutorial Room'),
    ]

    block          = models.ForeignKey(Block, on_delete=models.CASCADE, related_name='classrooms')
    room_number    = models.CharField(max_length=20)
    room_type      = models.CharField(max_length=10, choices=ROOM_TYPES, default='LECTURE')
    capacity       = models.IntegerField(default=60)
    has_projector  = models.BooleanField(default=True)
    has_ac         = models.BooleanField(default=False)
    has_smartboard = models.BooleanField(default=False)
    is_active      = models.BooleanField(default=True)

    class Meta:
        ordering = ['block', 'room_number']
        unique_together = ('block', 'room_number')

    def __str__(self):
        return f"{self.block.code}-{self.room_number} ({self.get_room_type_display()})"

    @property
    def current_enrollment(self):
        """Total students currently enrolled in courses using this room"""
        return Enrollment.objects.filter(
            course__classroom=self,
            is_active=True
        ).values('student').distinct().count()

    @property
    def utilization_percent(self):
        if self.capacity == 0:
            return 0
        return round((self.current_enrollment / self.capacity) * 100, 1)

    @property
    def utilization_status(self):
        pct = self.utilization_percent
        if pct >= 90:
            return 'overcrowded'
        elif pct >= 70:
            return 'high'
        elif pct >= 40:
            return 'moderate'
        else:
            return 'low'


# ─────────────────────────────────────────
# COURSE
# Academic course linked to classroom & faculty
# ─────────────────────────────────────────
class Course(models.Model):

    SEMESTER_CHOICES = [(i, f'Semester {i}') for i in range(1, 9)]

    name        = models.CharField(max_length=150)
    code        = models.CharField(max_length=20, unique=True)
    department = models.ForeignKey(Department,on_delete=models.SET_NULL,null=True,related_name='resource_courses')    
    faculty     = models.ForeignKey(Faculty, on_delete=models.SET_NULL, null=True, related_name='resource_courses')
    classroom   = models.ForeignKey(Classroom, on_delete=models.SET_NULL, null=True, related_name='courses')
    semester    = models.IntegerField(choices=SEMESTER_CHOICES, default=1)
    credits     = models.IntegerField(default=3)
    hours_per_week = models.IntegerField(default=3,
        help_text='Contact hours per week')
    max_students = models.IntegerField(default=60)
    is_active   = models.BooleanField(default=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f"{self.code} — {self.name}"

    @property
    def enrolled_count(self):
        return self.enrollments.filter(is_active=True).count()

    @property
    def enrollment_percent(self):
        if self.max_students == 0:
            return 0
        return round((self.enrolled_count / self.max_students) * 100, 1)


# ─────────────────────────────────────────
# ENROLLMENT
# Student enrolled in a course
# ─────────────────────────────────────────
class Enrollment(models.Model):

    GRADE_CHOICES = [
        ('O',  'Outstanding'),
        ('A+', 'Excellent'),
        ('A',  'Very Good'),
        ('B+', 'Good'),
        ('B',  'Above Average'),
        ('C',  'Average'),
        ('F',  'Fail'),
        ('-',  'Not Graded'),
    ]

    student     = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='resource_enrollments')
    course      = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrollments')
    enrolled_on = models.DateField(auto_now_add=True)
    grade       = models.CharField(max_length=2, choices=GRADE_CHOICES, default='-')
    is_active   = models.BooleanField(default=True)

    class Meta:
        unique_together = ('student', 'course')

    def __str__(self):
        return f"{self.student} → {self.course.code}"


# ─────────────────────────────────────────
# WORKLOAD RECORD
# Tracks faculty teaching hours per semester
# Used for workload distribution analysis
# ─────────────────────────────────────────
class WorkloadRecord(models.Model):

    STATUS_CHOICES = [
        ('NORMAL',    'Normal'),
        ('OVERLOADED','Overloaded'),
        ('UNDERLOAD', 'Underloaded'),
    ]

    faculty          = models.ForeignKey(Faculty, on_delete=models.CASCADE, related_name='workload_records')
    semester         = models.IntegerField()
    academic_year    = models.CharField(max_length=9, default='2024-25')
    total_courses    = models.IntegerField(default=0)
    total_hours_week = models.IntegerField(default=0)
    total_students   = models.IntegerField(default=0)
    status           = models.CharField(max_length=10, choices=STATUS_CHOICES, default='NORMAL')
    calculated_on    = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('faculty', 'semester', 'academic_year')

    def __str__(self):
        return f"{self.faculty} | Sem {self.semester} | {self.total_hours_week}h/wk | {self.status}"

    @property
    def hours_per_day(self):
        return round(self.total_hours_week / 5, 1)  # 5 working days