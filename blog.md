# I Built a Remedial Code System for Make-Up Classes — Here's Every Decision I Made

*Random code generation, time-windowed activation, fraud prevention, and an AI slot scorer — all in Django*

---

Every university student has experienced this: a faculty member cancels a class, a WhatsApp message goes out saying "make-up on Saturday 9 AM Block 32 Room 101", half the class doesn't see it, the other half shows up but there's no official attendance record, and by next week everyone's forgotten it happened.

Module 4 of my LPU Smart Campus Management System replaces that informal chaos with a proper digital workflow. Faculty schedules the class, the system generates a unique remedial code, faculty activates it when the session begins, students enter it on their phones, and a separate attendance record gets created — distinct from regular class attendance.

Here's how I built each piece, and why I made the decisions I did.

---

## The Core Idea: Time-Windowed Codes

The central design question was: how do students prove they physically attended the make-up class?

Options I considered:
- **QR code scan** — needs a camera, can be screenshotted and shared remotely
- **GPS check-in** — GPS spoofing is trivial on Android
- **Manual faculty entry** — defeats the automation purpose
- **Alphanumeric remedial code** — simple, fast, and the faculty controls the window

I went with a **6-character alphanumeric code** that only works during an explicit time window. The faculty activates it when the session starts and closes it when it ends. A student who wasn't there can't mark attendance because they don't have the code — and even if someone shares the code over WhatsApp, the 30-minute window limits the damage.

The code generation is one line:

```python
def generate_remedial_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
```

`random.choices` with 36 possible characters (26 uppercase + 10 digits) gives 36⁶ = over 2 billion possible codes. For a university context, collision probability is negligible, and Django's `unique=True` on the field catches the rare case anyway.

---

## The Session Model: Activation vs Creation

The `MakeUpSession` model has two distinct time concepts that tripped me up initially:

```python
class MakeUpSession(models.Model):
    date       = models.DateField()       # When the class is
    start_time = models.TimeField()       # Scheduled start
    end_time   = models.TimeField()       # Scheduled end

    code_active       = models.BooleanField(default=False)
    code_activated_at = models.DateTimeField(null=True, blank=True)
    code_expires_at   = models.DateTimeField(null=True, blank=True)
```

The `date/start_time/end_time` trio is the *scheduled* time — for display purposes. The `code_activated_at/code_expires_at` pair is the *actual* window during which students can mark attendance. Faculty might schedule a class for 10:00–11:00 AM but activate the code at 10:07 when everyone has settled in, and close it at 10:40 when they start the actual session.

Separating these two concepts kept the model clean and the UI honest.

The activation method is straightforward:

```python
def activate_code(self, duration_minutes=30):
    self.code_active       = True
    self.code_activated_at = timezone.now()
    self.code_expires_at   = timezone.now() + timedelta(minutes=duration_minutes)
    self.status = 'ONGOING'
    self.save()
```

And validity checking is a `@property` so every template can use it directly:

```python
@property
def is_code_valid(self):
    if not self.code_active:
        return False
    if self.code_expires_at and timezone.now() > self.code_expires_at:
        return False
    return True
```

---

## The Student UI: Six Boxes, Not One Field

My first version of the student attendance form was a single text input:

```html
<input type="text" name="code" maxlength="6" placeholder="Enter 6-char code">
```

It worked but felt cheap. Students made typos, used lowercase, added spaces. I rebuilt it as six individual input boxes — one per character — with auto-advance:

```javascript
box.addEventListener('input', (e) => {
    const val = e.target.value.replace(/[^a-zA-Z0-9]/g, '').toUpperCase();
    box.value = val;
    if (val && idx < boxes.length - 1) {
        boxes[idx + 1].focus();  // auto-advance to next box
    }
    syncHidden();
});
```

The regex `[^a-zA-Z0-9]` strips any non-alphanumeric character as the student types — so spaces, hyphens, and special characters get removed instantly. `.toUpperCase()` normalises case so "a3x7k2" and "A3X7K2" both work.

The six boxes feed into a hidden input that gets submitted:

```javascript
function syncHidden() {
    const code = Array.from(boxes).map(b => b.value).join('');
    hidden.value = code;
    submitBtn.disabled = code.length !== 6;
}
```

Submit stays disabled until all six boxes are filled — no accidental partial submissions.

I also added paste support. If a student receives the code via WhatsApp and pastes it:

```javascript
box.addEventListener('paste', (e) => {
    e.preventDefault();
    const pasted = (e.clipboardData.getData('text') || '')
        .replace(/[^a-zA-Z0-9]/g, '').toUpperCase();
    pasted.split('').slice(0, 6).forEach((char, i) => {
        if (boxes[i]) { boxes[i].value = char; }
    });
    syncHidden();
});
```

Paste on any box fills all six from the beginning. This small detail makes the experience feel polished.

---

## Five-Layer Validation

When the form submits, the view checks five conditions in sequence before creating an attendance record:

```python
# 1. Format check
if not code or len(code) != 6:
    messages.error(request, 'Please enter a valid 6-character code.')

# 2. Session exists
try:
    session = MakeUpSession.objects.get(remedial_code=code)
except MakeUpSession.DoesNotExist:
    messages.error(request, 'Invalid code.')

# 3. Code is active and not expired
if not session.is_code_valid:
    messages.error(request, 'Code is not active or has expired.')

# 4. Student is enrolled in this course
if not student.courses.filter(id=session.course.id).exists():
    messages.error(request, 'You are not enrolled in this course.')

# 5. Not already marked
if MakeUpAttendance.objects.filter(session=session, student=student).exists():
    messages.warning(request, 'Already marked for this session.')

# All clear — create record
MakeUpAttendance.objects.create(
    session=session, student=student,
    status='PRESENT', code_used=code,
    ip_address=request.META.get('REMOTE_ADDR')
)
```

The `unique_together = ('session', 'student')` constraint on the model is the final safety net — even if somehow two simultaneous requests slip through the Python check, the database will reject the duplicate.

I also store the `ip_address` and `code_used` (a snapshot of the code at the time of marking). This creates an audit trail — if suspicious patterns emerge (ten students from the same IP address), an admin can investigate.

---

## The Live Countdown Timer

The session detail page shows a countdown timer that depletes in real time. This required passing the expiry time from Django to JavaScript without a complex API call.

I used Django's template system to embed the timestamp directly:

```html
{% if session.is_code_valid and session.code_expires_at %}
<script>
  const expiresAt  = new Date("{{ session.code_expires_at|date:'c' }}");
  const now        = new Date();
  let totalSeconds = Math.max(0, Math.floor((expiresAt - now) / 1000));
  let maxSeconds   = totalSeconds;
  startCountdown();
</script>
{% endif %}
```

The `|date:'c'` filter outputs ISO 8601 format (`2026-02-22T10:30:00+05:30`) which JavaScript's `Date()` constructor parses reliably across browsers.

The countdown updates every second:

```javascript
function startCountdown() {
    timer = setInterval(() => {
        totalSeconds = Math.max(0, totalSeconds - 1);
        const m = Math.floor(totalSeconds / 60);
        const s = totalSeconds % 60;
        timerEl.textContent = `${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
        barEl.style.width = (totalSeconds / maxSeconds * 100) + '%';
        if (totalSeconds <= 0) clearInterval(timer);
    }, 1000);
}
```

The progress bar shrinks in sync with the countdown — giving faculty a quick visual sense of how much window remains without reading the numbers.

---

## The AI Scheduling System

After a make-up class is scheduled, the AI generates three slot recommendations for potential future sessions. This runs as part of the `schedule_session` view, immediately after the `MakeUpSession` is created:

```python
suggestions = get_scheduling_suggestions(session)
for s in suggestions:
    SchedulingSuggestion.objects.create(
        session        = session,
        suggested_date = s['date'],
        suggested_time = s['time'],
        score          = s['score'],
        reason         = s['reason'],
    )
```

The scoring function evaluates every time slot in the next 14 days across four dimensions:

```python
WEIGHT_GAP_FROM_LAST = 30   # days since last session
WEIGHT_MORNING_PREF  = 20   # earlier in day = better
WEIGHT_NO_CONFLICT   = 40   # biggest weight — is faculty free?
WEIGHT_DAY_BALANCE   = 10   # fewer existing sessions on this day

score = gap_score + time_score + conflict_score + day_score
```

The highest weight goes to conflict checking — a slot where the faculty already has another session is nearly useless, so it gets penalised heavily. Morning preference is based on the well-established principle that cognitive retention is higher in the morning.

The reason string is assembled from human-readable parts:

```python
reason_parts = []
if 2 <= gap <= 4:
    reason_parts.append(f"good gap of {gap} days from last session")
if t.hour <= 11:
    reason_parts.append("morning slot — better learning retention")
if t not in booked_slots[candidate_date]:
    reason_parts.append("faculty is free at this time")

reason = ' · '.join(reason_parts)
# → "morning slot — better learning retention · faculty is free · good gap of 3 days"
```

This explainability is important — faculty shouldn't have to trust a black box. Seeing the reason lets them agree or override the suggestion with confidence.

---

## What I'd Do Differently

**Push notifications.** When a faculty activates the code, enrolled students should get an instant notification — not rely on checking the dashboard. Django Channels with WebSockets, or a simple email/SMS trigger, would make this production-ready.

**Biometric confirmation.** The code system prevents remote marking but not physical proxy attendance — a friend can share their phone. Face recognition at code entry (like Module 1's AI attendance) would close this gap completely.

**Code as QR.** Displaying the remedial code as a QR code on a classroom projector — faculty full-screens it, students scan it — would be faster than typing 6 characters. The code itself stays the same; the display format changes.

---

## What I Built

Module 4 delivers a complete make-up class management system with:

- Unique 6-character remedial codes, auto-generated with `random.choices`
- Time-windowed code activation with live countdown timer
- 5-layer student attendance validation with IP logging
- Six-box code entry UI with auto-advance and paste support
- Separate `MakeUpAttendance` model — completely distinct from regular attendance
- AI scheduling suggestions with weighted scoring and explainable reasons
- Faculty dashboard with quick activate/close controls on each session card

The whole module required zero external libraries — pure Django, vanilla JavaScript, and a scoring function written in 60 lines of Python.

---

*This is Module 4 of my LPU Smart Campus Management System. Previous modules covered AI face recognition attendance, food pre-ordering, and campus resource estimation.*

*Built with Django 5, Bootstrap 5, and a lot of thought about what makes a code "hard to abuse."*

---

**Tags:** `Python` `Django` `Web Development` `University Projects` `Security`
