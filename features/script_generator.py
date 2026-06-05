"""
features/script_generator.py
Core Script Generation Engine — with Self-Improvement Loop

Accepts either:
  - Legacy: subject, topic, subtopic (maps to iraqi-moe-2024 curriculum)
  - Generic: curriculum_id, path_args (works with any curriculum in registry)

Every script generated benefits from what worked across ALL content creators.
"""

import json
import logging
import os
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)

DEFAULT_CURRICULUM_ID = os.getenv('DEFAULT_CURRICULUM_ID', 'iraqi-moe-2024')
DEFAULT_TZ = os.getenv('TIMEZONE', 'UTC')


class ScriptGenerator:
    """
    Full pipeline:
        MetricsEngine (platform patterns) → DataLoader / CurriculumLoader
        → CallawayFramework → YoutubePackager → Claude (script)
        → ContentValidator → Dedup → result dict
    """

    def __init__(self, provider, data_loader, callaway, packager, validator, dedup,
                 metrics=None, curriculum_loader=None):
        self.provider         = provider
        self.data_loader      = data_loader
        self.curriculum_loader = curriculum_loader
        self.callaway         = callaway
        self.packager         = packager
        self.validator        = validator
        self.dedup            = dedup
        self.metrics          = metrics

    def generate(
        self,
        subject: str = None,
        topic: str = None,
        subtopic: str = None,
        duration_minutes: int = 14,
        hook_archetype: str = 'default',
        curriculum_id: str = None,
        path_args: dict = None,
        generation_config: dict = None,
    ) -> dict:
        """
        Generate a complete YouTube script.

        Args:
            subject, topic, subtopic: Legacy positional curriculum path.
            curriculum_id:            Registry curriculum ID (overrides defaults).
            path_args:                Generic path dict e.g. {subject: 'chemistry', topic: 'X'}.
            duration_minutes:         Target video length (125 words/min).
            hook_archetype:           Archetype key (from curriculum metadata or 'default').
            generation_config:        Optional org-level overrides dict.

        Returns:
            Result dict with success=True and all script fields,
            or success=False with an error message.
        """
        try:
            # Resolve curriculum_id and path_args from legacy params if needed
            if not curriculum_id:
                curriculum_id = DEFAULT_CURRICULUM_ID
            if not path_args and subject:
                path_args = {'subject': subject, 'topic': topic, 'subtopic': subtopic}

            # Resolve display names from path_args
            display_subject  = path_args.get('subject') or subject or ''
            display_topic    = path_args.get('topic') or topic or ''
            display_subtopic = path_args.get('subtopic') or subtopic or ''

            # 1. Load curriculum metadata
            curriculum_meta = {}
            if self.curriculum_loader:
                curriculum_meta = self.curriculum_loader.registry.get_curriculum(curriculum_id) or {}

            # 2. Load content
            curriculum = {}
            if self.curriculum_loader and path_args:
                curriculum = self.curriculum_loader.get_content(curriculum_id, path_args)
            elif self.data_loader:
                curriculum = self.data_loader.get_curriculum_content(
                    display_subject, display_topic, display_subtopic)

            curriculum_text = json.dumps(curriculum)[:2000]
            target_words    = duration_minutes * 125
            num_sections    = max(3, duration_minutes // 3)

            # 3. Self-improvement loop
            performance_context = ''
            if self.metrics:
                try:
                    performance_context = self.metrics.get_platform_prompt_context(limit=10)
                except Exception as e:
                    logger.warning(f"Self-improvement loop failed (non-fatal): {e}")

            # 4. YouTube packaging
            hook  = self.packager.generate_hook(display_subject, display_topic, hook_archetype)
            title = self.packager.generate_title(display_subject, display_topic, hook_archetype)

            # 5. Callaway story framework
            direction = self.callaway.generate_story_direction(display_topic, curriculum_text)
            lens      = self.callaway.generate_story_lens(display_topic, display_subject)
            beats     = self.callaway.generate_story_beats(display_topic, num_sections)

            # 6. Build prompt — curriculum-aware
            language = curriculum_meta.get('language', 'ar')
            lang_instruction = (
                "Maintain natural, conversational Arabic tone."
                if language == 'ar'
                else f"Write in {language}. Maintain a natural, engaging tone."
            )

            prompt = f"""You are an expert educational video scriptwriter.

Curriculum: {curriculum_meta.get('name', curriculum_id)}
Subject: {display_subject}
Topic: {display_topic}
Subtopic: {display_subtopic}
Target length: {target_words} words
Hook archetype: {hook_archetype}

Curriculum reference:
{curriculum_text}

Story framework:
- Direction (final line): {direction}
- Lens (unique angle): {lens}
- Beats: {json.dumps(beats)[:500] if beats else 'None'}

{performance_context}

Write a complete YouTube script that:
1. Opens with this hook: {hook}
2. Teaches the core concepts from the curriculum reference
3. Uses storytelling (not lecturing)
4. Varies sentence length for rhythm
5. Builds toward the direction: {direction}
6. {lang_instruction}
7. Includes transition phrases between sections
8. Ends with a memorable closing statement

Target: {target_words} words
Format: Plain text, divide into {num_sections} sections

Script:"""

            script_content = self.provider.complete(
                [{"role": "user", "content": prompt}], max_tokens=4000
            ).strip()

            # 7. Validate
            validation = self.validator.validate_coverage(
                script_content, curriculum, display_subject, display_topic,
                curriculum_id=curriculum_id
            )

            # 8. Dedup + rhythm
            is_duplicate = self.dedup.check_and_register(script_content)
            rhythm       = self.callaway.analyze_rhythm(script_content)

            # 9. Thumbnail
            thumbnail_prompt = self.packager.generate_thumbnail_prompt(
                display_subject, display_topic, title)

            tz = pytz.timezone(DEFAULT_TZ) if DEFAULT_TZ != 'UTC' else pytz.utc

            return {
                'success':             True,
                'curriculum_id':       curriculum_id,
                'subject':             display_subject,
                'topic':               display_topic,
                'subtopic':            display_subtopic,
                'path_args':           path_args,
                'title':               title,
                'hook':                hook,
                'hook_archetype':      hook_archetype,
                'thumbnail_prompt':    thumbnail_prompt,
                'script_content':      script_content,
                'word_count':          len(script_content.split()),
                'callaway_direction':  direction,
                'callaway_lens':       lens,
                'callaway_beats':      beats,
                'validation':          validation,
                'is_duplicate':        is_duplicate,
                'rhythm_analysis':     rhythm,
                'used_performance_data': bool(performance_context),
                'generated_at':        datetime.now(tz).isoformat(),
            }

        except Exception as e:
            logger.error(f"Script generation error: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}
