# 📅 Module 4 — Make-Up Class & Remedial Code System

![Python](https://img.shields.io/badge/Python-3.11-blue?style=flat-square&logo=python)
![Django](https://img.shields.io/badge/Django-5.x-green?style=flat-square&logo=django)
![SQLite](https://img.shields.io/badge/Database-SQLite-lightgrey?style=flat-square)
![Status](https://img.shields.io/badge/Status-Complete-brightgreen?style=flat-square)

> Part of the **LPU Smart Campus Management System** — a multi-module Django project built for university digitization.

---

## 📌 Problem Statement

When a faculty member misses a class due to a holiday, illness, or campus event, students lose that lecture permanently unless a make-up class is scheduled. Currently this process is informal — a WhatsApp message, a notice on the board — with no way to officially track attendance for make-up sessions separately from regular ones.

This module solves it with a complete digital workflow:
- Faculty schedules a make-up class through the system
- A **unique 6-character remedial code** is generated automatically
- Faculty activates the code when the session begins — it expires after a set time window
- Students enter the code on their dashboard to mark attendance
- A **separate attendance record** is maintained for make-up classes
- AI suggests optimal future scheduling slots based on load and gaps

---

## ✨ Features

### 👨‍🏫 Faculty Features
- Schedule make-up classes with date, time, venue, and reason
- Unique 6-character alphanumeric remedial code auto-generated per session
- **Activate the code** for a configurable window (15 / 30 / 45 / 60 minutes)
- Live countdown timer on session detail page
- **Regenerate code** if it gets leaked — old code becomes instantly invalid
- **Close attendance** when session ends — status updates to Completed
- View live attendance as students mark in (auto-refresh every 8 seconds)
- Dashboard showing all upcoming and completed sessions

### 🎓 Student Features
- 6-box code entry UI — type or paste the remedial code
- Auto-advance between boxes, auto-submit when 6th character entered
- System validates: correct code, code is active, student is enrolled, not already marked
- Session list shows all make-up classes for enrolled courses
- 🟡 **Code Active** badge appears live when faculty activates the code
- Full history of attended make-up sessions

### 🤖 AI Scheduling (Bonus)
- After scheduling, AI generates **top 3 slot recommendations** for future sessions
- Scoring algorithm based on 4 factors:
  - Gap from last session (ideal: 2–4 days)
  - Time of day preference (mornings score higher)
  - Faculty availability (conflict check)
  - Day load balance (fewer sessions on that day = higher score)
- Scores displayed with human-readable reason (e.g. *"morning slot · faculty is free · good gap of 3 days"*)

### 🔔 Automatic Fraud Prevention
- IP address recorded at time of attendance marking
- Code expires automatically after the faculty-set window
- `unique_together` constraint prevents a student from marking twice
- Code only valid when faculty explicitly activates it

---

## 🗂️ Project Structure

```
lpu_cms/
├── makeup/
│   ├── models.py           # 3 models: MakeUpSession, MakeUpAttendance, SchedulingSuggestion
│   ├── views.py            # 9 views — faculty, student, AJAX
│   ├── urls.py             # 9 URL routes
│   ├── ai_scheduler.py     # AI slot scoring algorithm
│   └── admin.py            # Admin with inline attendance
│
└── templates/makeup/
    ├── faculty_dashboard.html  # Sessions list + quick activate/close
    ├── schedule_session.html   # Create make-up class form
    ├── session_detail.html     # Live code box + countdown + attendance
    └── student_dashboard.html  # 6-box code entry + session history
```

---

## 🗄️ Database Models

| Model | Purpose | Key Fields |
|-------|---------|-----------|
| `MakeUpSession` | One make-up class session | `faculty`, `course`, `date`, `remedial_code`, `code_active`, `code_expires_at`, `status` |
| `MakeUpAttendance` | Student attendance record for a session | `session`, `student`, `code_used`, `ip_address`, `marked_at` |
| `SchedulingSuggestion` | AI-generated slot recommendation | `session`, `suggested_date`, `suggested_time`, `score`, `reason` |

### Key Model Methods

```python
# Auto-generate a unique 6-character code
def generate_remedial_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

# Check if code is currently valid (active + not expired)
@property
def is_code_valid(self):
    if not self.code_active:
        return False
    if self.code_expires_at and timezone.now() > self.code_expires_at:
        return False
    return True

# Activate code for a time window
def activate_code(self, duration_minutes=30):
    self.code_active       = True
    self.code_activated_at = timezone.now()
    self.code_expires_at   = timezone.now() + timedelta(minutes=duration_minutes)
    self.status = 'ONGOING'
    self.save()

# Generate a brand new code (old one becomes instantly invalid)
def regenerate_code(self):
    self.remedial_code = generate_remedial_code()
    self.save()
```

---

## 🔗 URL Routes

| URL | View | Who |
|-----|------|-----|
| `/makeup/` | `faculty_dashboard` | Faculty |
| `/makeup/schedule/` | `schedule_session` | Faculty |
| `/makeup/session/<id>/` | `session_detail` | Faculty |
| `/makeup/session/<id>/activate/` | `activate_code` | Faculty |
| `/makeup/session/<id>/deactivate/` | `deactivate_code` | Faculty |
| `/makeup/session/<id>/regenerate/` | `regenerate_code` | Faculty |
| `/makeup/student/` | `student_dashboard` | Student |
| `/makeup/mark/` | `mark_attendance` | Student |
| `/makeup/api/status/<id>/` | `code_status_api` | AJAX |

---

## 🤖 AI Scheduling Algorithm

The AI scorer evaluates every candidate date+time slot in the next 14 days and returns the top 3 recommendations.

### Scoring Formula

```
Score = Gap Score + Time Score + Conflict Score + Day Load Score

Gap Score (max 30):
  2–4 days since last session → 30 pts  (ideal recovery gap)
  5+ days                     → 15 pts  (too long but acceptable)
  <2 days                     →  5 pts  (too soon)

Time Score (max 20):
  8 AM – 11 AM  → 20 pts  (peak learning hours)
  12 PM – 2 PM  → 10 pts  (early afternoon)
  3 PM+         →  5 pts  (fatigue zone)

Conflict Score (max 40):
  Faculty free at this slot   → 40 pts
  Faculty already booked      → -20 pts  (heavy penalty)

Day Load Score (max 10):
  0 sessions on this day      → 10 pts
  1 session on this day       →  5 pts
  2+ sessions on this day     →  0 pts
```

### Example Output
```
Suggestion 1: Wednesday 9:00 AM — Score: 95
  "morning slot · faculty is free · good gap of 3 days · no other sessions on this day"

Suggestion 2: Thursday 10:00 AM — Score: 80
  "morning slot · faculty is free · adequate gap of 4 days"

Suggestion 3: Friday 8:00 AM — Score: 65
  "morning slot · faculty is free · 1 session already on this day"
```

### Viva Answer
> *"The AI uses a weighted scoring system that evaluates candidate slots across four dimensions: temporal gap from the last session, time-of-day preference based on learning research, conflict detection from existing faculty sessions, and day load balance. Each dimension contributes a maximum score, and slots are ranked by total score. The results are stored as SchedulingSuggestion records linked to the session."*

---

## 🛡️ Attendance Validation Logic

When a student submits a remedial code, the system checks all 5 conditions in order:

```python
# 1. Code format valid (6 chars, alphanumeric)
if not code or len(code) != 6:
    → Error: "Please enter a valid 6-character code"

# 2. Session exists with this code
try:
    session = MakeUpSession.objects.get(remedial_code=code)
except MakeUpSession.DoesNotExist:
    → Error: "Invalid code"

# 3. Code is currently active and not expired
if not session.is_code_valid:
    → Error: "Code not active" / "Code has expired"

# 4. Student is enrolled in this course
if not student.courses.filter(id=session.course.id).exists():
    → Error: "You are not enrolled in this course"

# 5. Student hasn't already marked
if MakeUpAttendance.objects.filter(session=session, student=student).exists():
    → Error: "Already marked"

# All checks passed → mark attendance
MakeUpAttendance.objects.create(session=session, student=student, ...)
```

---

## 👥 User Roles

| Role | Access |
|------|--------|
| **Faculty** | Schedule sessions, activate/deactivate code, view attendance, see AI suggestions |
| **Student** | Enter remedial code, view make-up sessions for enrolled courses, see attendance history |
| **Admin** | Full access via Django admin — view all sessions, attendances, suggestions |
| **Stall Owner** | No access — separate module |

---

## ⚙️ Setup & Run

```bash
# 1. Activate virtual environment
lpu_env\Scripts\activate          # Windows
source lpu_env/bin/activate       # Mac/Linux

# 2. Apply migrations
python manage.py makemigrations makeup
python manage.py migrate

# 3. Start server
python manage.py runserver
```

---

## 🧪 Test Walkthrough

```
Step 1 — Log in as faculty
        → /makeup/schedule/
        → Fill form: select course, date, time, venue
        → Submit → note the 6-character remedial code

Step 2 — Log in as student (different browser/incognito)
        → /makeup/student/
        → Note the session appears in the list

Step 3 — Back as faculty → /makeup/session/<id>/
        → Click "Activate Code Now" (30 min window)
        → Countdown timer starts

Step 4 — Back as student
        → /makeup/student/
        → Session shows "🟡 Code Active" badge
        → Enter the 6-character code in the boxes
        → Click Mark Attendance
        → ✅ Success message

Step 5 — Faculty sees attendance update
        → /makeup/session/<id>/
        → Student name appears in attendance list
        → Attendance count increments

Step 6 — Faculty clicks "Close Attendance"
        → Status → Completed
        → Code deactivated
```

---

## 🔑 Key Django Concepts Used

| Concept | Where Used |
|---------|-----------|
| `random.choices` | `generate_remedial_code()` — cryptographically reasonable unique code |
| `unique_together` | One attendance per student per session — prevents duplicates |
| `auto_now_add` | `marked_at`, `created_at` — auto timestamps |
| `timedelta` | `code_expires_at = now + timedelta(minutes=duration)` |
| `update_or_create` | WorkloadRecord upsert in AI scheduler |
| `@property` | `is_code_valid`, `attendance_count`, `attendance_percent` |
| `JsonResponse` | `code_status_api` — AJAX polling for live status |
| `request.META.get('REMOTE_ADDR')` | IP address capture for fraud prevention |
| `values_list(flat=True)` | Get list of marked student IDs for unmarked calculation |
| `exclude(id__in=...)` | Find students not yet marked |

---

## 📁 Related Modules

| Module | Description |
|--------|-------------|
| [Module 1](../attendance/) | Smart Attendance System with AI Face Recognition |
| [Module 2](../food/) | Smart Food Stall Pre-Ordering System |
| [Module 3](../resources/) | Campus Resource & Parameter Estimation |
| Module 4 | **Make-Up Class & Remedial Code System** ← you are here |

---
