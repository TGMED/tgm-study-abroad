"""Builds Amara's system prompt for 1:1 chat and community replies, combining
the ported TGM knowledge base (services/knowledge_base.py) with the student's
ROI-calculator profile.
"""
from services import knowledge_base as kb

# Only the destination's own knowledge is included per call (not all five) --
# smaller/cheaper prompt, and matches how a real counsellor would triage.
DESTINATION_KB = {
    "uk": kb.KB_UK,
    "canada": kb.KB_CANADA,
    "ireland": kb.KB_IRELAND,
    "poland": kb.KB_POLAND,
    "germany": kb.KB_GERMANY,
}

COMMUNITY_ROOMS = ("uk", "canada", "ireland", "usa", "europe")

# Display metadata for each community room (label + country-code badge).
COMMUNITY_ROOM_META = {
    "uk": {"label": "United Kingdom", "code": "GB", "blurb": "Students & pros across the UK"},
    "canada": {"label": "Canada", "code": "CA", "blurb": "PGWP, PR routes & campus life"},
    "ireland": {"label": "Ireland", "code": "IE", "blurb": "EU tech hub & English-taught study"},
    "usa": {"label": "United States", "code": "US", "blurb": "F-1, OPT & the American route"},
    "europe": {"label": "Europe", "code": "EU", "blurb": "Schengen, affordable tuition & more"},
}

AMARA_PERSONA = (
    "You are Amara, TGM Education's study-abroad AI counsellor. TGM Education is a "
    "Nigeria-based study-abroad consultancy. You speak warmly, clearly, and practically "
    "-- like a knowledgeable counsellor, not a generic chatbot. Use the knowledge base "
    "below as your source of truth for costs, visas, timelines, and partner "
    "universities/programmes. If something isn't covered by the knowledge base, say so "
    "honestly rather than guessing, and suggest the student speak to a human TGM "
    "counsellor for specifics."
)


def _profile_block(profile):
    if not profile:
        return ""
    lines = ["STUDENT PROFILE (from their Global Education ROI calculator result):"]
    if profile.get("email"):
        lines.append(f"- Email: {profile['email']}")
    if profile.get("profession"):
        lines.append(f"- Current profession: {profile['profession']}")
    if profile.get("city"):
        lines.append(f"- Current city: {profile['city']}")
    if profile.get("salary"):
        lines.append(f"- Current monthly salary: ₦{profile['salary']:,.0f}")
    if profile.get("destination"):
        lines.append(f"- Target study destination: {profile['destination']}")
    if profile.get("qualification"):
        grade = f" ({profile['grade']})" if profile.get("grade") else ""
        lines.append(f"- Highest qualification: {profile['qualification']}{grade}")
    if profile.get("score") is not None:
        lines.append(f"- ROI score: {profile['score']}/100")
    if profile.get("ratio") is not None:
        lines.append(f"- Projected earning-uplift ratio: {profile['ratio']}x")
    return "\n".join(lines)


def build_chat_system_prompt(profile, opening=False):
    destination = ((profile or {}).get("destination") or "").lower()
    dest_kb = DESTINATION_KB.get(destination, "")
    parts = [AMARA_PERSONA, kb.KB_GENERAL, dest_kb, kb.KB_DOC_GEN, _profile_block(profile)]
    if opening:
        parts.append(
            "The student has just completed the ROI calculator and has not sent a "
            "message yet. Proactively open the conversation yourself: greet them by "
            "their profession and destination, reference their actual ROI score and "
            "earning-uplift ratio, and suggest 2-3 concrete next steps or course/"
            "programme directions given their profile. Do not wait for them to speak "
            "first, and do not say you are waiting for input."
        )
    return "\n\n".join(p for p in parts if p)


def build_community_system_prompt(room):
    dest_kb = DESTINATION_KB.get(room, "")
    parts = [
        AMARA_PERSONA,
        kb.KB_GENERAL,
        dest_kb,
        (
            "You are replying inside a public community discussion thread among "
            "several students, not in a private 1:1 chat -- keep your reply concise "
            "and generally useful to everyone reading the thread, not just the person "
            "who mentioned you."
        ),
    ]
    return "\n\n".join(p for p in parts if p)
