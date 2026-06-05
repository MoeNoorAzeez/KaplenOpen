"""
features/study_tips.py
Study Tips Script Generator
Generates study technique scripts without requiring S3 curriculum content.
Useful for general educational content not tied to a specific subject.
"""

import json
import logging
import os
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)

_TZ_NAME = os.getenv('TIMEZONE', 'UTC')
APP_TZ = pytz.timezone(_TZ_NAME) if _TZ_NAME != 'UTC' else pytz.utc


class StudyTipsGenerator:
    """
    Generates study technique / meta-learning scripts.
    No S3 curriculum required — topic is freeform.
    """

    def __init__(self, client, model, callaway, packager, dedup):
        """
        Args:
            client:   anthropic.Anthropic instance
            model:    model string
            callaway: features.callaway.CallawayFramework
            packager: features.youtube_packager.YoutubePackager
            dedup:    features.dedup.Dedup
        """
        self.client   = client
        self.model    = model
        self.callaway = callaway
        self.packager = packager
        self.dedup    = dedup

    def generate(
        self,
        tip_topic: str,
        duration_minutes: int = 14,
        hook_archetype: str = 'teacher',
    ) -> dict:
        """
        Generate a study tips / techniques script.

        Args:
            tip_topic:        e.g. 'How to memorize faster', 'Pomodoro technique'
            duration_minutes: target video length (125 words/min)
            hook_archetype:   teacher | relatable | question | story | surprising | problem

        Returns:
            Result dict with success=True and all script fields,
            or success=False with an error message.
        """
        try:
            target_words = duration_minutes * 125
            num_sections = max(3, duration_minutes // 3)

            # YouTube packaging
            hook  = self.packager.generate_hook('General', tip_topic, hook_archetype)
            title = self.packager.generate_title('General', tip_topic, hook_archetype)

            # Callaway story framework
            direction = self.callaway.generate_story_direction(tip_topic, "")
            lens      = self.callaway.generate_story_lens(tip_topic, 'General')
            beats     = self.callaway.generate_story_beats(tip_topic, num_sections)

            prompt = f"""You are an expert educational content creator specializing in study techniques for Iraqi students.

Topic: {tip_topic}
Target length: {target_words} words
Hook archetype: {hook_archetype}

Story framework:
- Direction (final line): {direction}
- Lens (unique angle): {lens}
- Beats: {json.dumps(beats)[:500] if beats else 'None'}

Write a complete YouTube script about study techniques that:
1. Opens with this hook: {hook}
2. Teaches {num_sections} practical study methods
3. Uses storytelling (not lecturing)
4. Includes personal, relatable examples
5. Varies sentence length for rhythm
6. Is actionable and immediately useful
7. Builds toward the direction: {direction}
8. Maintains natural, conversational Arabic tone

Target: {target_words} words
Divide into {num_sections} practical sections

Script:"""

            message = self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                messages=[{"role": "user", "content": prompt}]
            )
            script_content = message.content[0].text.strip()

            is_duplicate     = self.dedup.check_and_register(script_content)
            rhythm           = self.callaway.analyze_rhythm(script_content)
            thumbnail_prompt = self.packager.generate_thumbnail_prompt('General', tip_topic, title)

            return {
                'success':           True,
                'topic':             tip_topic,
                'title':             title,
                'hook':              hook,
                'hook_archetype':    hook_archetype,
                'thumbnail_prompt':  thumbnail_prompt,
                'script_content':    script_content,
                'word_count':        len(script_content.split()),
                'callaway_direction': direction,
                'callaway_lens':     lens,
                'callaway_beats':    beats,
                'is_duplicate':      is_duplicate,
                'rhythm_analysis':   rhythm,
                'generated_at':      datetime.now(APP_TZ).isoformat(),
            }

        except Exception as e:
            logger.error(f"Study tips generation error: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}
