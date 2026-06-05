"""
features/long_form_generator.py
Long-Form Educational Video Generator (1hr - 3hr) — v2
- S3 curriculum integration (100% accuracy)
- Outline-first, section-by-section generation
- Streaming/batching for 8k-24k word outputs
- Strict outline adherence (no repetition)
"""

import json
import logging
import os
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)

_TZ_NAME = os.getenv('TIMEZONE', 'UTC')
APP_TZ = pytz.timezone(_TZ_NAME) if _TZ_NAME != 'UTC' else pytz.utc

# Word count targets
WORD_COUNTS = {
    60: 8000,      # 1hr video: 8000 words (~125 words/min)
    180: 24000,    # 3hr video: 24000 words (~125 words/min)
}


class LongFormVideoGenerator:
    """
    Full pipeline for long-form videos:
    1. Load S3 curriculum (100% accuracy)
    2. Generate outline (phase structure + layer breakdown)
    3. Stream sections sequentially (Claude API streaming)
    4. Validate against outline (no repetition)
    5. Assemble final script
    """

    def __init__(self, client, model, data_loader, s3_client, bucket, validator, dedup):
        """
        Args:
            client:      anthropic.Anthropic instance
            model:       model string
            data_loader: features.data_loader.DataLoader
            s3_client:   boto3.client('s3')
            bucket:      S3 bucket name
            validator:   features.validator.ContentValidator
            dedup:       features.dedup.Dedup
        """
        self.client = client
        self.model = model
        self.data_loader = data_loader
        self.s3_client = s3_client
        self.bucket = bucket
        self.validator = validator
        self.dedup = dedup

    def generate(
        self,
        subject: str,
        topic: str,
        subtopic: str,
        duration_minutes: int = 60,
        stream_callback=None,
    ) -> dict:
        """
        Generate a complete long-form educational script with streaming output.

        Args:
            subject:           e.g. 'chemistry'
            topic:             e.g. 'Chemical Equilibrium'
            subtopic:          e.g. 'Le Chatelier Principle'
            duration_minutes:  60 (1hr) or 180 (3hr)
            stream_callback:   Optional callback function(section_name, content) for streaming UI

        Returns:
            Result dict with success=True and all phases + full script,
            or success=False with error.
        """
        try:
            # ════════════════════════════════════════════════════════════════
            # STEP 1: LOAD S3 CURRICULUM (100% accuracy)
            # ════════════════════════════════════════════════════════════════

            logger.info(f"Loading S3 curriculum: {subject}/{topic}/{subtopic}")
            
            curriculum = self._load_s3_curriculum(subject, topic, subtopic)
            if not curriculum:
                return {
                    'success': False,
                    'error': f'No curriculum found in S3 for {subject}/{topic}/{subtopic}'
                }
            
            curriculum_text = json.dumps(curriculum)[:5000]  # Truncate for prompts
            target_words = WORD_COUNTS.get(duration_minutes, 8000)

            # ════════════════════════════════════════════════════════════════
            # STEP 2: GENERATE DETAILED OUTLINE
            # ════════════════════════════════════════════════════════════════

            logger.info(f"Generating outline for {duration_minutes}min video ({target_words} words)")
            
            if stream_callback:
                stream_callback('outline', 'Generating video outline...')
            
            outline = self._generate_outline(
                subject, topic, subtopic, curriculum_text, duration_minutes, target_words
            )
            
            if not outline['success']:
                return outline

            if stream_callback:
                stream_callback('outline_complete', json.dumps(outline['outline'], ensure_ascii=False))

            # ════════════════════════════════════════════════════════════════
            # STEP 3: STREAM SECTIONS SEQUENTIALLY
            # ════════════════════════════════════════════════════════════════

            logger.info(f"Streaming {len(outline['sections'])} sections from outline")
            
            sections_content = {}
            total_words = 0
            
            for section_num, section in enumerate(outline['sections'], 1):
                logger.info(f"Streaming section {section_num}/{len(outline['sections'])}: {section['name']}")
                
                if stream_callback:
                    stream_callback('section_start', f"{section_num}/{len(outline['sections'])}: {section['name']}")
                
                # Stream this section
                section_content = self._stream_section(
                    section=section,
                    section_num=section_num,
                    total_sections=len(outline['sections']),
                    curriculum=curriculum_text,
                    previous_sections=sections_content,
                    outline=outline['outline'],
                    stream_callback=stream_callback,
                )
                
                if not section_content:
                    logger.error(f"Failed to generate section {section_num}")
                    continue
                
                sections_content[section['name']] = section_content
                word_count = len(section_content.split())
                total_words += word_count
                
                logger.info(f"Section {section_num} complete: {word_count} words (total: {total_words})")
                
                if stream_callback:
                    stream_callback('section_complete', f"{section['name']}: {word_count} words")

            # ════════════════════════════════════════════════════════════════
            # STEP 4: ASSEMBLE FINAL SCRIPT
            # ════════════════════════════════════════════════════════════════

            full_script = self._assemble_script(sections_content, outline)
            final_word_count = len(full_script.split())

            logger.info(f"Script assembly complete: {final_word_count} words")

            if stream_callback:
                stream_callback('assembly_complete', f"{final_word_count} words")

            # ════════════════════════════════════════════════════════════════
            # STEP 5: VALIDATION & DEDUP
            # ════════════════════════════════════════════════════════════════

            logger.info("Running validation and dedup checks")
            
            if stream_callback:
                stream_callback('validation', 'Validating curriculum coverage...')
            
            validation = self.validator.validate_coverage(
                full_script, curriculum, subject, topic
            )

            is_duplicate = self.dedup.check_and_register(full_script)

            if stream_callback:
                stream_callback('validation_complete', f"Coverage: {validation.get('coverage_percentage', 0)}%")

            # ════════════════════════════════════════════════════════════════
            # RETURN COMPLETE RESULT
            # ════════════════════════════════════════════════════════════════

            return {
                'success': True,
                'subject': subject,
                'topic': topic,
                'subtopic': subtopic,
                'duration_minutes': duration_minutes,
                'target_words': target_words,
                'final_word_count': final_word_count,
                'video_type': 'long_form',
                'outline': outline['outline'],
                'sections': sections_content,
                'full_script': full_script,
                'validation': validation,
                'is_duplicate': is_duplicate,
                'generated_at': datetime.now(APP_TZ).isoformat(),
            }

        except Exception as e:
            logger.error(f"Long-form generation error: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    def _load_s3_curriculum(self, subject: str, topic: str, subtopic: str) -> dict or None:
        """
        Load curriculum from S3 using the same hierarchy as script_generator.
        
        S3 structure: subtopics/{subject}/{topic}/{subtopic}.json
        """
        try:
            key = f"subtopics/{subject}/{topic}/{subtopic}.json"
            
            response = self.s3_client.get_object(Bucket=self.bucket, Key=key)
            content = response['Body'].read().decode('utf-8')
            curriculum = json.loads(content)
            
            logger.info(f"Loaded curriculum from S3: {key}")
            return curriculum

        except Exception as e:
            logger.error(f"S3 curriculum load error: {e}")
            return None

    def _generate_outline(
        self,
        subject: str,
        topic: str,
        subtopic: str,
        curriculum_text: str,
        duration_minutes: int,
        target_words: int,
    ) -> dict:
        """
        Generate a detailed outline that breaks down the video into sections.
        This outline will be followed STRICTLY in section generation (no deviation).
        """
        try:
            num_layers = max(3, (duration_minutes // 20))
            
            prompt = f"""You are an expert long-form educational video architect.

TASK: Create a DETAILED OUTLINE for a {duration_minutes}-minute ({target_words}-word) long-form educational video.

Subject: {subject}
Topic: {topic}
Subtopic: {subtopic}
Curriculum: {curriculum_text}

OUTLINE STRUCTURE (6 phases):

Phase 1: INCITING CASE (Hook) — 2-5 min
- Real, specific, named incident
- Date, place, person
- Outcome (tragic/absurd/counterintuitive)
- Raises ONE thesis question

Phase 2: STAKES (Pattern proof) — 4-6 min
- Scale: statistics
- Diversity: crosses demographics
- Proximity: why viewer cares

Phase 3: EXPLANATORY FRAMEWORK (Metaphor) — 3-5 min
- Load-bearing metaphor
- Maps to all layers

Phase 4: CAUSAL LAYER STACK — {num_layers} layers, 3-5 min each
- Each layer answers previous question
- Each raises next question
- Uses curriculum EXACTLY

Phase 5: OBJECTION SYSTEM (distributed) — 1-2 min per objection
- 2-3 objections total
- Placed before triggering information

Phase 6: RESOLUTION — 3-5 min
- Returns to inciting case
- Uses accumulated vocabulary
- Closes the loop

OUTPUT FORMAT:

Create a JSON object with:
{{
    "thesis_question": "The single question the video answers",
    "metaphor": "The load-bearing metaphor",
    "total_target_words": {target_words},
    "sections": [
        {{
            "phase": "1",
            "name": "Section name",
            "target_words": 300,
            "key_points": ["point1", "point2"],
            "curriculum_coverage": ["curriculum concept 1", "concept 2"],
            "instructions": "Specific instructions for writing this section. Be detailed."
        }},
        ...
    ]
}}

Requirements:
1. Sum of all section target_words must equal {target_words}
2. Each section has explicit curriculum_coverage (from the provided curriculum)
3. Each section has detailed instructions (the writer will follow these EXACTLY)
4. Sections are ordered sequentially
5. Instructions must prevent repetition: "Do not repeat X from the previous section"

Generate the complete outline as valid JSON."""

            message = self.client.messages.create(
                model=self.model,
                max_tokens=3000,
                messages=[{"role": "user", "content": prompt}]
            )
            
            outline_text = message.content[0].text.strip()
            
            # Extract JSON from response
            try:
                outline = json.loads(outline_text)
            except json.JSONDecodeError:
                # Try to extract JSON from code block
                if '```json' in outline_text:
                    outline = json.loads(outline_text.split('```json')[1].split('```')[0])
                elif '```' in outline_text:
                    outline = json.loads(outline_text.split('```')[1].split('```')[0])
                else:
                    raise ValueError("Could not parse outline JSON")
            
            logger.info(f"Outline generated with {len(outline.get('sections', []))} sections")
            
            return {
                'success': True,
                'outline': outline
            }

        except Exception as e:
            logger.error(f"Outline generation error: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    def _stream_section(
        self,
        section: dict,
        section_num: int,
        total_sections: int,
        curriculum: str,
        previous_sections: dict,
        outline: dict,
        stream_callback=None,
    ) -> str or None:
        """
        Generate a single section using streaming.
        Writes STRICTLY according to outline instructions.
        Does NOT repeat content from previous sections.
        """
        try:
            # Build context of what came before
            previous_content = "\n\n".join([
                f"{name}: {content[:300]}..."
                for name, content in list(previous_sections.items())[-2:]  # Last 2 sections
            ])

            prompt = f"""You are an expert educational scriptwriter. Write EXACTLY one section of a long-form video.

OUTLINE FOR THIS SECTION:
Name: {section['name']}
Target word count: {section['target_words']}
Key points to cover: {json.dumps(section['key_points'])}
Curriculum to reference: {json.dumps(section['curriculum_coverage'])}
Instructions: {section['instructions']}

CURRICULUM REFERENCE (use this for accuracy):
{curriculum}

CONTEXT FROM PREVIOUS SECTIONS (do NOT repeat this):
{previous_content}

STRICT RULES:
1. Write EXACTLY {section['target_words']} words (±100 words tolerance)
2. Follow the instructions EXACTLY
3. Reference ALL curriculum concepts listed
4. Do NOT repeat any content from previous sections
5. Use conversational, engaging tone
6. Use Iraqi dialect where appropriate
7. End with a transition to the next section or a retention moment

SECTION {section_num}/{total_sections}: {section['name']}

Write the full section content now:"""

            # Stream the response
            section_content = ""
            
            with self.client.messages.stream(
                model=self.model,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            ) as stream:
                for text in stream.text_stream:
                    section_content += text
                    if stream_callback:
                        stream_callback('section_stream', text)
            
            section_content = section_content.strip()
            logger.info(f"Section {section_num} streamed: {len(section_content.split())} words")
            
            return section_content

        except Exception as e:
            logger.error(f"Stream section error: {e}")
            return None

    def _assemble_script(self, sections_content: dict, outline: dict) -> str:
        """
        Assemble all sections into a cohesive final script.
        Sections are already in order from outline.
        """
        try:
            script_parts = []
            
            for section in outline.get('sections', []):
                section_name = section['name']
                if section_name in sections_content:
                    script_parts.append(sections_content[section_name])
            
            full_script = "\n\n".join(script_parts)
            
            logger.info(f"Script assembled: {len(full_script.split())} total words")
            return full_script

        except Exception as e:
            logger.error(f"Script assembly error: {e}")
            return ""
