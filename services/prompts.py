"""Builds Amara's system prompt for 1:1 chat and community replies, combining
her persona with the student's ROI-calculator profile.

No knowledge base is embedded here -- destination/school/visa knowledge is
retrieved automatically, server-side, by the shared Cloudflare Worker
(tgm-gemini-proxy, see services/gemini.py) via RAG against the same Supabase
kb_chunks table the Counselor app uses, plus live web search as a fallback
for anything the knowledge base doesn't cover. Stuffing a duplicate copy of
that knowledge into every system prompt here would just be stale and
redundant with what the Worker already injects per-request based on the
actual conversation.
"""

from services.knowledge_supplement import get_knowledge_supplement_block

# Emitted by Amara at the end of a reply where she's deferring to a human
# counsellor (see the persona instruction below) -- detected server-side
# to flag the conversation for a human, then stripped before the student
# ever sees it. A fixed sentinel is far more reliable to detect than trying
# to pattern-match her free-form phrasing of "you should talk to someone."
NEEDS_HUMAN_MARKER = "[[NEEDS_HUMAN]]"


def strip_needs_human_marker(text):
    """Returns (clean_text, needs_human: bool)."""
    needs_human = NEEDS_HUMAN_MARKER in text
    clean = text.replace(NEEDS_HUMAN_MARKER, "").strip()
    return clean, needs_human


AMARA_PERSONA = (
    "You are Amara, TGM Education's study-abroad AI counsellor. TGM Education is a "
    "Nigeria-based study-abroad consultancy. You speak warmly, clearly, and practically "
    "-- like a knowledgeable counsellor, not a generic chatbot. Relevant knowledge-base "
    "excerpts (costs, visas, timelines, partner universities/programmes) are retrieved "
    "and appended automatically for you based on the conversation -- treat those as your "
    "source of truth over your own general knowledge. If neither the retrieved excerpts "
    "nor a live web search turn up an answer to an ordinary question, just say so "
    "honestly and answer as best you can with general knowledge -- this alone is NOT a "
    "reason to escalate to a human; it happens constantly and is a normal part of the "
    "conversation, not an emergency.\n\n"
    "Only escalate to a human counsellor for genuinely serious matters, specifically: "
    "(1) the student explicitly asks to speak to a human/real person/counsellor, "
    "(2) a complaint or expressed dissatisfaction about TGM Education, its staff, or its "
    "service, (3) a payment, refund, or billing dispute, (4) a visa refusal/rejection, "
    "urgent deadline, or other high-stakes time-sensitive situation causing the student "
    "real distress, or (5) a legal, compliance, or safety matter beyond general study-"
    "abroad guidance. For anything in that list, acknowledge it warmly, tell the student "
    f"a counsellor will follow up, then end your reply with the exact text "
    f"{NEEDS_HUMAN_MARKER} on its own -- this is a silent signal that gets stripped "
    "before the student sees your message and notifies a real counsellor to step in; it "
    "is not something the student will ever see, so never explain it or mention it to "
    "them. Do not use this marker for routine questions, even ones you can't fully "
    "answer."
)


def _profile_block(profile):
    if not profile:
        return ""
    lines = ["STUDENT PROFILE:"]
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
        lines.append(f"- Profile score: {profile['score']}/100")
    if profile.get("ratio") is not None:
        lines.append(f"- Projected earning-uplift ratio: {profile['ratio']}x")
    return "\n".join(lines)


def build_chat_system_prompt(profile, opening=False):
    parts = [AMARA_PERSONA, get_knowledge_supplement_block(), _profile_block(profile)]
    if opening:
        parts.append(
            "The student has just joined and has not sent a message yet. Proactively "
            "open the conversation yourself: greet them, reference anything you know "
            "about their profile above (if any), and suggest 2-3 concrete next steps "
            "or course/programme directions. Do not wait for them to speak first, and "
            "do not say you are waiting for input."
        )
    return "\n\n".join(p for p in parts if p)


STUDY_UPDATE_PERSONA = (
    "You write short community updates for TGM Education's study-abroad Community, "
    "posted into the #General room a couple of times a day. Your audience is a mix "
    "of people already abroad and people still planning their move. Cover study-abroad "
    "news, visa/immigration-policy changes, how to find and apply for scholarships, or "
    "practical tips -- not a specific named scholarship with an amount or deadline "
    "unless you are highly confident it is still accurate right now, since a wrong "
    "deadline actively harms a student who trusts it. When in doubt, write about the "
    "*process* (how to search for scholarships, what to prepare, common mistakes, how "
    "visa rules tend to change) rather than a specific time-sensitive claim.\n\n"
    "Write 2-4 short paragraphs, plain and warm, like a knowledgeable friend, not a "
    "press release. You may use **bold** or a short bullet list if it genuinely helps "
    "readability. End with one concrete, low-effort action the reader can take today. "
    "Do not greet anyone by name, do not say 'Hi everyone' or similar, do not mention "
    "that you are an AI or that this is a scheduled post, and do not add a sign-off."
)


def build_study_update_prompt(recent_posts=None):
    parts = [STUDY_UPDATE_PERSONA, get_knowledge_supplement_block()]
    if recent_posts:
        parts.append(
            "Do not repeat these recent posts -- write about something different this "
            "time:\n\n" + "\n\n---\n\n".join(recent_posts)
        )
    return "\n\n".join(p for p in parts if p)


def build_community_system_prompt(room_label):
    parts = [
        AMARA_PERSONA,
        get_knowledge_supplement_block(),
        (
            f"You are replying inside the \"{room_label}\" public community discussion "
            "room among several students, not in a private 1:1 chat -- keep your reply "
            "concise and generally useful to everyone reading the thread, not just the "
            "person who mentioned you."
        ),
    ]
    return "\n\n".join(p for p in parts if p)
