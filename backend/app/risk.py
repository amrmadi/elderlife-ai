"""Risk engine contract (swap the body for your ML model, keep the signature).
Input : checkin_delay_min, activity_ratio (vs personal baseline, None if no data), fall, fall_answered, missed_reminders (optional)
Output: {"level", "score", "reasons": [...]}
"""
LEVELS = ["Normal", "Low", "Medium", "High", "Critical"]
NEXT_STEP = {
    "Medium": "Ask the person: 'Are you okay?'",
    "High": "Notify the caregiver",
    "Critical": "Escalate to the emergency contact",
}

def assess(s: dict) -> dict:
    score, reasons = 0.0, []
    d = s["checkin_delay_min"]
    if d >= 120:
        score += 0.3; reasons.append("No check-in for over 2 hours")
    elif d >= 30:
        score += 0.15; reasons.append("Check-in is late")
    r = s["activity_ratio"]
    if r is not None and r < 0.5:
        score += 0.25; reasons.append(f"Activity {round((1 - r) * 100)}% below personal baseline")
    m = s.get("missed_reminders", 0)
    if m >= 2:
        score += 0.1; reasons.append(f"{m} care-plan reminders missed today")
    if s["fall"]:
        score += 0.3; reasons.append("Fall detected")
        if not s["fall_answered"]:
            score += 0.3; reasons.append("No response after fall")
    score = min(score, 1.0)
    level = LEVELS[0 if score < .1 else 1 if score < .25 else 2 if score < .5 else 3 if score < .75 else 4]
    return {"level": level, "score": round(score, 2), "reasons": reasons}
