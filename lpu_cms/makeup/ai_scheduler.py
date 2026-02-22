from django.utils import timezone
from datetime import timedelta, datetime, time
from collections import defaultdict


# ─────────────────────────────────────────
# SCORING WEIGHTS
# Adjust to change AI priorities
# ─────────────────────────────────────────
WEIGHT_GAP_FROM_LAST   = 30   # prefer slots 2-3 days after last class
WEIGHT_MORNING_PREF    = 20   # mornings preferred for learning retention
WEIGHT_NO_CONFLICT     = 40   # heavily penalise existing bookings
WEIGHT_DAY_BALANCE     = 10   # prefer days with fewer existing sessions

PREFERRED_TIMES = [
    time(8,  0),   # 8:00 AM
    time(9,  0),   # 9:00 AM
    time(10, 0),   # 10:00 AM
    time(11, 0),   # 11:00 AM
    time(14, 0),   # 2:00 PM
]


def get_scheduling_suggestions(session, num_suggestions=3):
    """
    AI Scheduling Algorithm:

    Scores candidate date+time slots for a make-up class based on:
    1. Gap from last session        — avoid back-to-back days
    2. Time of day preference       — mornings score higher
    3. Conflict check               — penalise if faculty already has a session
    4. Day load balance             — prefer less-busy days

    Returns top N suggestions sorted by score (highest first).
    """
    from .models import MakeUpSession

    today    = timezone.now().date()
    faculty  = session.faculty
    course   = session.course

    # Get existing sessions for this faculty in the next 14 days
    existing = MakeUpSession.objects.filter(
        faculty=faculty,
        date__gte=today,
        date__lte=today + timedelta(days=14),
        status__in=['SCHEDULED', 'ONGOING']
    ).exclude(pk=session.pk)

    # Map: date → list of start_times already booked
    booked_slots = defaultdict(list)
    for s in existing:
        booked_slots[s.date].append(s.start_time)

    # Count sessions per weekday (0=Mon ... 4=Fri)
    day_load = defaultdict(int)
    for s in existing:
        day_load[s.date.weekday()] += 1

    # Find last session date for this course
    last_session = MakeUpSession.objects.filter(
        course=course,
        status='COMPLETED'
    ).order_by('-date').first()
    last_date = last_session.date if last_session else today

    # ── GENERATE CANDIDATES ──
    candidates = []
    for day_offset in range(1, 15):  # look 14 days ahead
        candidate_date = today + timedelta(days=day_offset)

        # Skip Sundays
        if candidate_date.weekday() == 6:
            continue

        for t in PREFERRED_TIMES:
            score  = 0
            reason_parts = []

            # 1. Gap from last session (ideal = 2-3 days)
            gap = (candidate_date - last_date).days
            if 2 <= gap <= 4:
                score += WEIGHT_GAP_FROM_LAST
                reason_parts.append(f"good gap of {gap} days from last session")
            elif gap >= 5:
                score += WEIGHT_GAP_FROM_LAST // 2
                reason_parts.append(f"adequate gap of {gap} days")
            else:
                score += 5
                reason_parts.append("close to last session")

            # 2. Time of day preference
            if t.hour <= 11:
                score += WEIGHT_MORNING_PREF
                reason_parts.append("morning slot — better learning retention")
            elif t.hour <= 14:
                score += WEIGHT_MORNING_PREF // 2
                reason_parts.append("early afternoon slot")
            else:
                score += 5
                reason_parts.append("late afternoon slot")

            # 3. Conflict check — is faculty free?
            if t not in booked_slots[candidate_date]:
                score += WEIGHT_NO_CONFLICT
                reason_parts.append("faculty is free at this time")
            else:
                score -= 20
                reason_parts.append("⚠ faculty has another session at this time")

            # 4. Day load balance
            weekday_load = day_load[candidate_date.weekday()]
            if weekday_load == 0:
                score += WEIGHT_DAY_BALANCE
                reason_parts.append("no other sessions on this day")
            elif weekday_load == 1:
                score += WEIGHT_DAY_BALANCE // 2
            else:
                score += 0
                reason_parts.append(f"{weekday_load} sessions already on this day")

            candidates.append({
                'date':   candidate_date,
                'time':   t,
                'score':  min(score, 100),
                'reason': ' · '.join(reason_parts),
            })

    # Sort by score descending, return top N
    candidates.sort(key=lambda x: x['score'], reverse=True)
    return candidates[:num_suggestions]