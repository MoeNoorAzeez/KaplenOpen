"""
features/callaway.py
Callaway Storytelling Framework (v16)
Direction, Lens, Beats, Rhythm — the four pillars of script structure.
"""

import json
import re
import logging

logger = logging.getLogger(__name__)


class CallawayFramework:

    def __init__(self, provider):
        self.provider = provider

    def generate_story_direction(self, topic: str, curriculum_content: str) -> str:
        """
        Direction: The emotional destination.
        Write the FINAL LINE first. Then work backwards.
        The final line must be memorable and shareable.
        """
        try:
            prompt = f"""You are an expert scriptwriter specializing in story direction.

Topic: {topic}

Your task: Write the FINAL memorable line of this video.

The line must:
1. Be one sentence only
2. Be so memorable that if a viewer heard ONLY this line, they would share it
3. Create a twist or callback to the beginning
4. Feel inevitable and powerful when reached

This is the emotional destination — everything else in the video builds toward this.

Write the ideal final line now:"""

            return self.provider.complete(
                [{"role": "user", "content": prompt}], max_tokens=100
            ).strip()

        except Exception as e:
            logger.error(f"Direction generation error: {e}")
            return f"Master the complete story of {topic}"

    def generate_story_lens(self, topic: str, subject: str) -> str:
        """
        Lens: Your unique angle.
        Don't cover what everyone else covers.
        Find the 10% angle, not the 90% angle.
        """
        try:
            prompt = f"""You are an expert at finding unique story angles.

Subject: {subject}
Topic: {topic}

Your task: Write your UNIQUE LENS — your differentiated angle on this topic.

The lens must:
1. Be one sentence only
2. Answer: How are you different from everyone else?
3. Be uncommon (10% of creators would cover this, not 90%)
4. Be authentic (you can actually execute it)

Write your unique lens now:"""

            return self.provider.complete(
                [{"role": "user", "content": prompt}], max_tokens=100
            ).strip()

        except Exception as e:
            logger.error(f"Lens generation error: {e}")
            return f"The unique angle on {topic}"

    def generate_story_beats(self, topic: str, num_sections: int) -> list | None:
        """
        Beats: The dance between CONTEXT and CONFLICT.

        CONTEXT = setup, character, situation (closes loops)
        CONFLICT = disruption, problem, twist (opens loops)

        Use BUT and THEREFORE connectors. NEVER use AND THEN.
        """
        try:
            prompt = f"""You are an expert at Callaway-style story beats.

Topic: {topic}

Your task: Write {num_sections} story beats using the CONTEXT-CONFLICT dance.

RULES:
1. Alternate between CONTEXT (setup) and CONFLICT (disruption)
2. Use BUT for contradictions and conflicts
3. Use THEREFORE for consequences and escalations
4. NEVER use AND THEN
5. Each beat should raise a new question or escalate the story

Return as JSON array only (no preamble):
[
  {{"beat_number": 1, "type": "context", "connector": "", "content": "Starting situation or setup"}},
  {{"beat_number": 2, "type": "conflict", "connector": "BUT", "content": "Unexpected disruption"}},
  {{"beat_number": 3, "type": "consequence", "connector": "THEREFORE", "content": "The impact or escalation"}}
]

Generate {num_sections} beats now:"""

            response_text = self.provider.complete(
                [{"role": "user", "content": prompt}], max_tokens=1000
            ).strip()
            json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            return None

        except Exception as e:
            logger.error(f"Beats generation error: {e}")
            return None

    def analyze_rhythm(self, script: str) -> dict:
        """
        Analyze rhythm: Sentence length variation.
        Goal: Jagged edge (varied lengths) not flat line (same lengths).
        Higher variance = better rhythm score.
        """
        try:
            sentences = [s.strip() for s in re.split(r'[.!?]', script) if s.strip()]

            if not sentences:
                return {'score': 0, 'analysis': 'No sentences found'}

            lengths = [len(s.split()) for s in sentences]
            avg_length = sum(lengths) / len(lengths)
            variance = sum((l - avg_length) ** 2 for l in lengths) / len(lengths)
            rhythm_score = min(int(variance * 2), 100)

            return {
                'score': rhythm_score,
                'sentence_count': len(sentences),
                'avg_length': round(avg_length, 1),
                'min_length': min(lengths),
                'max_length': max(lengths),
                'analysis': (
                    'Good rhythm — varied sentence lengths'
                    if rhythm_score > 50
                    else 'Needs improvement — make sentences more varied'
                )
            }

        except Exception as e:
            logger.error(f"Rhythm analysis error: {e}")
            return {'score': 0, 'analysis': 'Error analyzing rhythm'}
