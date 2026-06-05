"""
features/youtube_packager.py
YouTube Packaging — Content Platform Edition

Implements the content differentiation architecture:
  - 5 title patterns with pattern stacking
  - Differentiation layer: pain point -> angle -> title (no two creators compete)
  - Thumbnail briefs calibrated to the edtech expression intensity scale (4-7)
  - Coherence check: thumbnail must deliver on title's cognitive promise

Iraqi-specific prompts are driven by the curriculum_id / language config,
not hardcoded. The fallback prompts use English placeholders.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ── Title patterns ────────────────────────────────────────────────────────────

TITLE_PATTERNS = [
    'curriculum_specificity',   # Pattern 1 — chapter + completeness signal
    'pain_point',               # Pattern 2 — student confusion + solution
    'exam_stakes',              # Pattern 3 — wazari urgency
    'density',                  # Pattern 4 — N topics in X minutes
    'credibility',              # Pattern 5 — teacher authority signal
]

# ── Content angles (differentiation layer) ───────────────────────────────────

CONTENT_ANGLES = [
    'comparison',               # difference between X and Y
    'mistake_analysis',         # top N mistakes students make
    'pattern_recognition',      # N patterns the wazari always tests
    'mechanism_explanation',    # what actually happens at the molecular level
    'step_by_step',             # solve X in N clear steps
    'real_world_connection',    # real-life application then wazari solution
    'reverse_engineering',      # if the wazari asks X, here is the core idea
    'simplification',           # the simplest possible explanation
    'misconceptions',           # most students believe X, but the truth is Y
    'speed_run',                # everything in N minutes for last-minute prep
]

# Pain point -> compatible angles in priority order
PAIN_TO_ANGLES = {
    'reversible_irreversible':      ['comparison', 'simplification', 'misconceptions', 'real_world_connection'],
    'equilibrium_constant_calc':    ['mistake_analysis', 'step_by_step', 'speed_run', 'reverse_engineering'],
    'direction_of_shift':           ['pattern_recognition', 'mechanism_explanation', 'step_by_step', 'misconceptions'],
    'dynamic_equilibrium':          ['mechanism_explanation', 'real_world_connection', 'simplification', 'comparison'],
    'le_chatelier':                 ['pattern_recognition', 'step_by_step', 'real_world_connection', 'misconceptions'],
    'units_decimals':               ['mistake_analysis', 'step_by_step', 'speed_run'],
    'homogeneous_heterogeneous':    ['comparison', 'simplification', 'misconceptions'],
    'general':                      CONTENT_ANGLES,
}

# Pain point + angle -> primary title pattern
PAIN_ANGLE_TO_PATTERN = {
    ('equilibrium_constant_calc', 'mistake_analysis'):   'exam_stakes',
    ('equilibrium_constant_calc', 'step_by_step'):        'density',
    ('equilibrium_constant_calc', 'speed_run'):           'density',
    ('direction_of_shift',        'pattern_recognition'): 'exam_stakes',
    ('direction_of_shift',        'mechanism_explanation'):'curriculum_specificity',
    ('reversible_irreversible',   'comparison'):           'pain_point',
    ('reversible_irreversible',   'simplification'):       'pain_point',
    ('dynamic_equilibrium',       'mechanism_explanation'):'curriculum_specificity',
    ('dynamic_equilibrium',       'real_world_connection'):'pain_point',
    ('le_chatelier',              'pattern_recognition'):  'exam_stakes',
}

# Generic words that signal low-quality titles — reject if present
GENERIC_WORDS = [
    'explained', 'lesson', 'tutorial', 'educational', 'video', 'learn', 'understand',
]

# Expression intensity guidance per pattern (edtech scale 4-7, never 9-10)
INTENSITY_GUIDE = {
    'curriculum_specificity': 'Expression intensity 5-6: confident, mid-explanation, professional',
    'pain_point':             'Expression intensity 4-5: warm, empathetic, open body language',
    'exam_stakes':            'Expression intensity 6-7: serious, focused, pointing at key info',
    'density':                'Expression intensity 5-6: organised, calm, not frantic',
    'credibility':            'Expression intensity 6: warm + authoritative, formal setting',
}

# Angle -> expected CTR range (reference only, not enforced)
ANGLE_CTR = {
    'comparison':            (6.5, 7.5),
    'mistake_analysis':      (7.0, 8.0),
    'pattern_recognition':   (8.0, 9.0),
    'mechanism_explanation': (5.5, 6.5),
    'step_by_step':          (6.0, 7.0),
    'real_world_connection': (5.0, 6.5),
    'reverse_engineering':   (7.0, 8.0),
    'simplification':        (5.5, 6.5),
    'misconceptions':        (6.5, 7.5),
    'speed_run':             (4.5, 5.5),
}


@dataclass
class CreatorProfile:
    """
    Optional content creator context for differentiated title generation.
    The more fields populated, the more specific and unique the output.

    Fields:
        username:           creator identifier
        years_experience:   years in the field
        credibility_type:   one of: expert | instructor | institution_based |
                            success_rate | specialist | testimonials | practitioner
        credibility_detail: human-readable credential
        pain_point:         key from PAIN_TO_ANGLES
        angle:              key from CONTENT_ANGLES; auto-selected if empty
        subject_grade:      e.g. 'sixth science', 'grade 10'
        exam_year:          current exam/cohort year as string e.g. '2026'
        assigned_angles:    angles already used by other creators for same pain point
    """
    username: str = ''
    years_experience: int = 0
    credibility_type: str = ''
    credibility_detail: str = ''
    pain_point: str = 'general'
    angle: str = ''
    subject_grade: str = ''
    exam_year: str = '2026'
    assigned_angles: list = field(default_factory=list)

    # Backward-compat property
    @property
    def wazari_year(self) -> str:
        return self.exam_year

    @wazari_year.setter
    def wazari_year(self, value: str):
        self.exam_year = value


# Backward-compat alias
TeacherProfile = CreatorProfile


class YoutubePackager:

    def __init__(self, client, model: str):
        self.client = client
        self.model  = model

    # ══════════════════════════════════════════════════════════════════════
    # PUBLIC API
    # ══════════════════════════════════════════════════════════════════════

    def generate_hook(
        self,
        subject: str,
        topic: str,
        archetype: str = 'teacher',
        teacher: Optional[TeacherProfile] = None,
    ) -> str:
        """
        Generate a one-sentence hook in Iraqi Arabic dialect calibrated to
        the edtech market.

        Archetypes:
            teacher     — extract a curriculum lesson from the content
            relatable   — connect to student daily experience or exam pressure
            question    — provocative question targeting a common confusion
            story       — short story revealing a mistake or insight
            surprising  — surprising wazari fact or exam pattern
            problem     — name the specific student pain point directly

        With a TeacherProfile the hook incorporates the teacher's assigned
        pain point and credibility signal for differentiation.
        """
        teacher_context = self._teacher_context_block(teacher) if teacher else ''

        try:
            prompt = (
                "You are a YouTube hook specialist for Iraqi educational content.\n"
                "Write only in Iraqi Arabic dialect.\n\n"
                f"Subject: {subject}\n"
                f"Topic: {topic}\n"
                f"Hook style: {archetype}\n"
                f"{teacher_context}\n\n"
                "Hook archetype guidelines:\n"
                "- teacher: extract a lesson — frame it as what the student will lose if they miss this\n"
                "- relatable: connect to exam pressure or daily experience\n"
                "- question: ask a provocative question about a famous student confusion\n"
                "- story: short story revealing a mistake or surprising insight\n"
                "- surprising: surprising wazari fact or exam pattern students don't know\n"
                "- problem: directly name the specific student pain point\n\n"
                "Rules:\n"
                "- One sentence only\n"
                "- Iraqi colloquial dialect\n"
                "- Must feel like something a student would stop scrolling for\n"
                "- No preamble, no explanation — hook only\n"
            )

            message = self.client.messages.create(
                model=self.model,
                max_tokens=150,
                messages=[{"role": "user", "content": prompt}]
            )
            return message.content[0].text.strip()

        except Exception as e:
            logger.error(f"Hook generation error: {e}")
            return f"This point will make the difference in your wazari exam: {topic}"

    def generate_title(
        self,
        subject: str,
        topic: str,
        hook_archetype: str = 'teacher',
        teacher: Optional[TeacherProfile] = None,
        chapter: str = '',
        stack_patterns: bool = True,
    ) -> str:
        """
        Generate an edtech-optimised YouTube title in Iraqi Arabic.

        Without TeacherProfile: generates a strong single-pattern title.
        With TeacherProfile:    generates a differentiated stacked title
                                using the teacher's assigned pain point,
                                angle, and credibility signal.

        Args:
            subject:         Subject name
            topic:           Specific topic or concept
            hook_archetype:  Hint for primary pattern selection
            teacher:         Optional TeacherProfile for differentiation
            chapter:         Chapter identifier e.g. 'Chapter 2'
            stack_patterns:  Whether to stack 2-3 patterns (recommended True)
        """
        teacher_context = self._teacher_context_block(teacher) if teacher else ''
        chapter_hint    = f"Chapter/section: {chapter}" if chapter else ''
        wazari_year     = teacher.wazari_year if teacher else '2026'

        try:
            stack_instruction = (
                "Stack 2-3 patterns for maximum impact."
                if stack_patterns else
                "Use one strong pattern only."
            )

            prompt = (
                "You are a YouTube title expert for the highly competitive Iraqi edtech market.\n"
                "Write the title in Iraqi Arabic (mix of colloquial and formal as instructed).\n\n"
                f"Subject: {subject}\n"
                f"Topic: {topic}\n"
                f"{chapter_hint}\n"
                f"Wazari exam year: {wazari_year}\n"
                f"{teacher_context}\n\n"
                "=== THE FIVE EDTECH TITLE PATTERNS ===\n\n"
                "Pattern 1 — Curriculum Specificity (highest search intent):\n"
                "  Formula: [TOPIC] - Chapter [N] | [comprehensive/complete/everything you need]\n"
                "  Example structure: '[Topic] - Chapter 2 | Full explanation for [grade]'\n\n"
                "Pattern 2 — Pain Point Acknowledgment (highest browse CTR):\n"
                "  Formula: For those confused by [CONCEPT] - here is the complete solution\n"
                "  Use Iraqi colloquial dialect for the pain-point half\n\n"
                "Pattern 3 — Exam Stakes (highest urgency):\n"
                "  Formula: [CONCEPT] - this is the hardest part in the wazari | full explanation\n"
                "  Reference actual wazari exam years where possible\n\n"
                "Pattern 4 — Density (for efficient learners):\n"
                "  Formula: [Chapter] complete - [N] topics in [time]\n\n"
                "Pattern 5 — Teacher Credibility (trust building):\n"
                "  Formula: [credential] teacher explains [topic] - the right way\n\n"
                "=== MANDATORY RULES ===\n"
                f"- Title MUST contain a curriculum marker (chapter number, grade level, or wazari {wazari_year})\n"
                "- Use Iraqi colloquial dialect for pain points and empathy sections\n"
                "- Use formal Arabic for chapter names and exam references\n"
                "- NEVER use: 'easy explanation', 'simple', generic teaching words\n"
                "- Acceptable length: 10-18 words (students are searching, not just browsing)\n"
                f"- {stack_instruction}\n\n"
                "Write ONE title only, no explanation:\n"
            )

            message = self.client.messages.create(
                model=self.model,
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}]
            )

            title = message.content[0].text.strip()
            title = (
                title
                .replace("Title:", "")
                .replace("**", "")
                .replace("Suggested:", "")
                .strip()
            )

            if any(word in title.lower() for word in GENERIC_WORDS):
                return self._fallback_title(topic, chapter, wazari_year)

            return title

        except Exception as e:
            logger.error(f"Title generation error: {e}")
            return self._fallback_title(topic, chapter, wazari_year)

    def generate_thumbnail_prompt(
        self,
        subject: str,
        topic: str,
        title: str,
        pattern: str = 'curriculum_specificity',
        teacher: Optional[TeacherProfile] = None,
    ) -> str:
        """
        Generate a thumbnail design brief calibrated to the edtech
        expression intensity scale (4-7) and the detected title pattern.

        Expression intensity scale (edtech):
            4-5: warm, empathetic (pain point / credibility patterns)
            5-6: professional, confident (curriculum / density patterns)
            6-7: serious, intense (exam stakes pattern)
            9-10: AVOID — looks like clickbait, kills credibility with exam students

        Args:
            subject:  Subject name
            topic:    Topic or concept
            title:    The generated title (used for coherence check)
            pattern:  Primary title pattern from TITLE_PATTERNS
            teacher:  Optional TeacherProfile
        """
        intensity    = INTENSITY_GUIDE.get(pattern, 'Expression intensity 5-6: professional, confident')
        teacher_ctx  = self._teacher_context_block(teacher) if teacher else ''
        wazari_year  = teacher.wazari_year if teacher else '2026'

        try:
            prompt = (
                "You are a YouTube thumbnail designer specialising in Iraqi educational channels.\n\n"
                f"Title: {title}\n"
                f"Subject: {subject}\n"
                f"Topic: {topic}\n"
                f"Primary title pattern: {pattern}\n"
                f"{intensity}\n"
                f"{teacher_ctx}\n\n"
                "=== EDTECH THUMBNAIL RULES ===\n\n"
                "Key insight: Exam-prep students are skeptical and searching with intent.\n"
                "The thumbnail must say 'this is a real lesson' not 'clickbait content'.\n\n"
                "1. FACE AND EXPRESSION:\n"
                "   - curriculum_specificity: intensity 5-6, confident mid-explanation, at board\n"
                "   - pain_point: intensity 4-5, warm empathetic, open hands (I understand your problem)\n"
                "   - exam_stakes: intensity 6-7, serious focused, pointing at important item\n"
                "   - density: intensity 5-6, calm organised, not overwhelmed\n"
                "   - credibility: intensity 6, warm + authoritative, formal setting\n"
                "   - NEVER use 9-10 intensity — looks like clickbait, students back-click immediately\n\n"
                "2. SETTING:\n"
                "   - Classroom or teaching space (signals 'real lesson')\n"
                "   - Textbook or board visible if possible (confirms curriculum alignment)\n"
                "   - Professional lighting — not selfie lighting\n\n"
                "3. TEXT OVERLAY (max 3 elements, readable at 168x94px):\n"
                f"   - Primary: chapter number OR 'Wazari {wazari_year}' — minimum 20pt\n"
                "   - Secondary: 'comprehensive' or 'complete solution' — smaller\n"
                "   - Color: bright yellow or white text on dark navy or charcoal background\n"
                "   - NO trendy gradients or neon colors — professional contrast only\n\n"
                "4. COLOR STRATEGY BY PATTERN:\n"
                "   - curriculum_specificity: dark navy background + yellow/white text\n"
                "   - pain_point: warm gray or beige + green solution text\n"
                "   - exam_stakes: dark navy + red or gold text (high stakes feel)\n"
                "   - density: clean light background + bold blue or black text\n"
                "   - credibility: professional dark + gold text\n\n"
                "5. COHERENCE CHECK:\n"
                f"   The title promises: '{title[:50]}...'\n"
                "   The thumbnail must make the viewer feel: 'this person can deliver on that promise'\n\n"
                "Write the design brief directly, no preamble:\n"
            )

            message = self.client.messages.create(
                model=self.model,
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}]
            )

            result = (
                message.content[0].text.strip()
                .replace("Design:", "")
                .replace("**", "")
                .replace("Brief:", "")
                .strip()
            )
            return result

        except Exception as e:
            logger.error(f"Thumbnail generation error: {e}")
            return self._fallback_thumbnail(topic, pattern)

    def select_angle_for_teacher(
        self,
        pain_point: str,
        assigned_angles: list,
    ) -> str:
        """
        Select the best available content angle for a teacher's pain point,
        skipping angles already assigned to other teachers (deduplication).

        Args:
            pain_point:      Key from PAIN_TO_ANGLES
            assigned_angles: Angles already used by other teachers
                             for the same pain point on the same topic

        Returns:
            Best available angle string.
        """
        compatible = PAIN_TO_ANGLES.get(pain_point, CONTENT_ANGLES)

        for angle in compatible:
            if angle not in assigned_angles:
                logger.info(f"Assigned angle '{angle}' for pain point '{pain_point}'")
                return angle

        # All primary angles for this pain point are taken — fall back to full list
        for angle in CONTENT_ANGLES:
            if angle not in assigned_angles:
                logger.warning(
                    f"All primary angles taken for pain point '{pain_point}', "
                    f"falling back to '{angle}'"
                )
                return angle

        logger.error(f"No available angles remaining for pain point '{pain_point}'")
        return 'comparison'

    def generate_differentiated_package(
        self,
        subject: str,
        topic: str,
        teacher: TeacherProfile,
        chapter: str = '',
    ) -> dict:
        """
        Full differentiation pipeline for a single teacher:
            1. Auto-select angle if not already set on profile
            2. Detect primary title pattern from pain + angle
            3. Generate title
            4. Generate thumbnail brief
            5. Generate search targets
            6. Return full package

        Args:
            subject:  Subject name
            topic:    Topic or concept
            teacher:  TeacherProfile (angle auto-selected if not set)
            chapter:  Chapter identifier

        Returns:
            {
                title,
                angle_used,
                pattern_used,
                thumbnail_brief,
                search_targets,
                expected_ctr_range,
            }
        """
        # Auto-select angle if not assigned
        if not teacher.angle:
            teacher.angle = self.select_angle_for_teacher(
                pain_point=teacher.pain_point,
                assigned_angles=teacher.assigned_angles,
            )

        pattern = PAIN_ANGLE_TO_PATTERN.get(
            (teacher.pain_point, teacher.angle),
            'curriculum_specificity'
        )

        title     = self.generate_title(subject, topic, teacher=teacher, chapter=chapter)
        thumbnail = self.generate_thumbnail_prompt(subject, topic, title, pattern, teacher)
        targets   = self._generate_search_targets(topic, teacher.pain_point, teacher.angle, teacher.wazari_year)
        ctr_range = ANGLE_CTR.get(teacher.angle, (5.0, 7.0))

        return {
            'title':             title,
            'angle_used':        teacher.angle,
            'pattern_used':      pattern,
            'thumbnail_brief':   thumbnail,
            'search_targets':    targets,
            'expected_ctr_range': ctr_range,
        }

    # ══════════════════════════════════════════════════════════════════════
    # PRIVATE HELPERS
    # ══════════════════════════════════════════════════════════════════════

    def _teacher_context_block(self, teacher: TeacherProfile) -> str:
        """Format teacher profile into a prompt context block (English labels only)."""
        lines = []
        if teacher.credibility_detail:
            lines.append(f"Teacher credential: {teacher.credibility_detail}")
        if teacher.pain_point and teacher.pain_point != 'general':
            lines.append(f"Student pain point to target: {teacher.pain_point.replace('_', ' ')}")
        if teacher.angle:
            lines.append(f"Content angle assigned: {teacher.angle.replace('_', ' ')}")
        if teacher.subject_grade:
            lines.append(f"Grade level: {teacher.subject_grade}")
        if teacher.years_experience:
            lines.append(f"Years of experience: {teacher.years_experience}")
        return '\n'.join(lines)

    def _generate_search_targets(
        self,
        topic: str,
        pain_point: str,
        angle: str,
        wazari_year: str,
    ) -> list:
        """
        Generate the search queries this title package should rank for.
        Queries are in Arabic — Claude generates these as Arabic strings,
        so we just build the structure here and note the topic as a placeholder.
        The actual Arabic query text will appear after Claude generates the title.
        """
        # These are English-side identifiers; the actual search queries
        # will be in Arabic based on the topic and angle combination.
        return [
            f"{topic} {angle.replace('_', ' ')}",
            f"{topic} wazari {wazari_year}",
            f"{topic} {pain_point.replace('_', ' ')}",
        ]

    def _fallback_title(self, topic: str, chapter: str, wazari_year: str) -> str:
        """Safe fallback — Pattern 1 + Pattern 3 stack, no Arabic hardcoded."""
        chapter_part = f" - {chapter}" if chapter else ''
        return f"{topic}{chapter_part} | Complete Explanation (Wazari {wazari_year})"

    def _fallback_thumbnail(self, topic: str, pattern: str) -> str:
        """Safe fallback thumbnail brief."""
        intensity = INTENSITY_GUIDE.get(pattern, 'Expression intensity 5-6: professional, confident')
        return (
            f"Teacher with {intensity} in a classroom or teaching setting. "
            f"Primary text overlay: chapter number or topic name '{topic}' in bold yellow "
            f"on dark navy background, minimum 20pt. "
            f"Maximum 3 text elements. Readable at 168x94px. "
            f"No trendy gradients. Professional contrast only."
        )
