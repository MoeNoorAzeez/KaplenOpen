"""
features/essay_generator.py
Professional Essay/Article Generator — Premium Hidden Feature
- Takes uploaded MD source material (any topic)
- Uses 6-phase long-form architecture
- Generates 5k-30k word essays in English
- 500-word chunks merged per section
- Audience field drives tone/framing instructions
- Outline-first, section-by-section generation
- Streaming output
- Requires special account flag: is_essay_author=true
"""

import json
import logging
import os
from datetime import datetime
import pytz
import hashlib
import math

logger = logging.getLogger(__name__)

_TZ_NAME = os.getenv('TIMEZONE', 'UTC')
APP_TZ = pytz.timezone(_TZ_NAME) if _TZ_NAME != 'UTC' else pytz.utc

# Word count targets by essay type
ESSAY_WORD_COUNTS = {
    'short': 5000,
    'medium': 12000,
    'long': 30000,
    # YouTube script modes — spoken-word format, timed sections
    'youtube_10': 1400,   # ~10 min video
    'youtube_15': 2100,   # ~15 min video
    'youtube_25': 3600,   # ~25 min video
}

YOUTUBE_DURATIONS = {
    'youtube_10': 10,
    'youtube_15': 15,
    'youtube_25': 25,
}

CHUNK_SIZE = 500  # words per generation chunk


class EssayGenerator:
    """
    Professional essay/article generator using 6-phase architecture.
    All output is in English.
    Audience field is used as framing/POV instructions passed to Claude.
    Each section is generated in 500-word chunks then merged.
    """

    def __init__(self, provider, validator=None, dedup=None):
        self.provider = provider
        self.validator = validator
        self.dedup = dedup

    def generate(
        self,
        title: str,
        source_material: str,
        essay_type: str = 'medium',
        tone: str = 'academic',
        target_audience: str = 'educated general reader',
        stream_callback=None,
    ) -> dict:
        """
        Generate a professional English essay from source material.

        target_audience is used as framing instructions:
        e.g. "Iraqi university students skeptical of Western economics"
        → Claude frames arguments accordingly.
        """
        try:
            if essay_type not in ESSAY_WORD_COUNTS:
                return {
                    'success': False,
                    'error': f'essay_type must be one of: {list(ESSAY_WORD_COUNTS.keys())}'
                }

            is_youtube = essay_type.startswith('youtube')
            target_words = ESSAY_WORD_COUNTS[essay_type]
            duration_minutes = YOUTUBE_DURATIONS.get(essay_type)
            mode_label = f"{duration_minutes}-min YouTube script" if is_youtube else f"{essay_type} essay"
            logger.info(f"Generating {mode_label}: '{title}' ({target_words} words)")

            # ── STEP 1: ANALYZE SOURCE MATERIAL ──────────────────────────────
            if stream_callback:
                stream_callback('analysis', 'Analyzing source material...')

            analysis = self._analyze_source_material(source_material, title)

            if stream_callback:
                stream_callback('analysis_complete', f"Identified {len(analysis['key_themes'])} key themes")

            # ── STEP 2: GENERATE OUTLINE ──────────────────────────────────────
            if stream_callback:
                stream_callback('outline', 'Generating script outline...' if is_youtube else 'Generating essay outline...')

            outline = self._generate_youtube_outline(
                title=title,
                source_material=source_material,
                analysis=analysis,
                duration_minutes=duration_minutes,
                target_words=target_words,
                style=tone,
                viewer_description=target_audience,
            ) if is_youtube else self._generate_outline(
                title=title,
                source_material=source_material,
                analysis=analysis,
                essay_type=essay_type,
                target_words=target_words,
                tone=tone,
                target_audience=target_audience,
            )

            if not outline['success']:
                return outline

            if stream_callback:
                stream_callback('outline_complete', f"Generated {len(outline['outline']['sections'])} sections")

            # ── STEP 3: GENERATE SECTIONS IN 500-WORD CHUNKS ─────────────────
            if stream_callback:
                stream_callback('generation', f"Generating {len(outline['outline']['sections'])} sections...")

            sections_content = {}
            total_words = 0

            for section_num, section in enumerate(outline['outline']['sections'], 1):
                logger.info(f"Generating section {section_num}/{len(outline['outline']['sections'])}: {section['name']}")

                if stream_callback:
                    stream_callback('section_start', f"{section_num}/{len(outline['outline']['sections'])}: {section['name']}")

                section_content = self._generate_section_chunked(
                    section=section,
                    section_num=section_num,
                    total_sections=len(outline['outline']['sections']),
                    source_material=source_material,
                    previous_sections=sections_content,
                    outline=outline['outline'],
                    tone=tone,
                    target_audience=target_audience,
                    stream_callback=stream_callback,
                    is_youtube=is_youtube,
                )

                if not section_content:
                    logger.error(f"Failed to generate section {section_num}")
                    continue

                sections_content[section['name']] = section_content
                word_count = len(section_content.split())
                total_words += word_count

                logger.info(f"Section {section_num} complete: {word_count} words")

                if stream_callback:
                    stream_callback('section_complete', f"{section['name']}: {word_count} words")

            # ── STEP 4: ASSEMBLE ──────────────────────────────────────────────
            full_essay = (
                self._assemble_script(title, sections_content, outline, duration_minutes)
                if is_youtube
                else self._assemble_essay(title, sections_content, outline)
            )
            final_word_count = len(full_essay.split())

            logger.info(f"Essay assembly complete: {final_word_count} words")

            if stream_callback:
                stream_callback('assembly_complete', f"{final_word_count} words")

            # ── STEP 5: VALIDATE ──────────────────────────────────────────────
            if stream_callback:
                stream_callback('validation', 'Validating essay...')

            validation = {}
            if self.validator:
                validation = self.validator.validate_coverage(full_essay, {}, '', '')

            is_duplicate = False
            if self.dedup:
                is_duplicate = self.dedup.check_and_register(full_essay)

            return {
                'success': True,
                'title': title,
                'essay_type': essay_type,
                'is_youtube': is_youtube,
                'duration_minutes': duration_minutes,
                'tone': tone,
                'target_audience': target_audience,
                'target_words': target_words,
                'final_word_count': final_word_count,
                'outline': outline['outline'],
                'sections': sections_content,
                'full_essay': full_essay,
                'source_hash': hashlib.md5(source_material.encode()).hexdigest(),
                'validation': validation,
                'is_duplicate': is_duplicate,
                'generated_at': datetime.now(APP_TZ).isoformat(),
            }

        except Exception as e:
            logger.error(f"Essay generation error: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    # ── PRIVATE METHODS ───────────────────────────────────────────────────────

    def _analyze_source_material(self, source_material: str, title: str) -> dict:
        try:
            prompt = f"""Analyze this source material and identify the core themes, arguments, and key concepts.
Write your analysis in English only.

Title: {title}

Source Material:
{source_material[:3000]}

Respond with JSON only, no preamble:
{{
    "key_themes": ["theme1", "theme2", "theme3"],
    "main_argument": "The central thesis or argument",
    "supporting_points": ["point1", "point2", "point3"],
    "potential_objections": ["objection1", "objection2"],
    "material_quality": "excellent/good/adequate"
}}"""

            text = self.provider.complete(
                [{"role": "user", "content": prompt}], max_tokens=1000
            ).strip()

            try:
                analysis = json.loads(text)
            except json.JSONDecodeError:
                if '```json' in text:
                    analysis = json.loads(text.split('```json')[1].split('```')[0])
                elif '```' in text:
                    analysis = json.loads(text.split('```')[1].split('```')[0])
                else:
                    analysis = {
                        'key_themes': ['topic'],
                        'main_argument': 'Main idea from source',
                        'supporting_points': ['point1', 'point2'],
                        'potential_objections': ['objection1'],
                        'material_quality': 'adequate'
                    }

            return analysis

        except Exception as e:
            logger.error(f"Analyze source error: {e}")
            return {
                'key_themes': ['topic'],
                'main_argument': 'Main argument',
                'supporting_points': ['support1', 'support2'],
                'potential_objections': [],
                'material_quality': 'adequate'
            }

    def _generate_outline(
        self,
        title: str,
        source_material: str,
        analysis: dict,
        essay_type: str,
        target_words: int,
        tone: str,
        target_audience: str,
    ) -> dict:
        try:
            num_sections = {
                'short': 5,
                'medium': 7,
                'long': 10,
            }.get(essay_type, 7)

            # Derive framing instructions from audience field
            framing = (
                f"Frame all arguments for this specific audience: {target_audience}. "
                f"Consider their prior knowledge, concerns, and likely objections when structuring the essay."
            )

            prompt = f"""Create a detailed English essay outline using the 6-phase architecture.

Title: {title}
Essay Type: {essay_type} ({target_words} words total)
Tone: {tone}
Audience & Framing: {framing}

Source Material Themes: {', '.join(analysis['key_themes'])}
Main Argument: {analysis['main_argument']}

6-PHASE STRUCTURE:
1. Hook/Opening (Why this matters)
2. Stakes (Why reader should care)
3. Framework (Core thesis and metaphor)
4. Analytical Stack ({num_sections - 4} layers of argument/analysis)
5. Counterarguments (Address objections)
6. Synthesis/Resolution

Generate JSON outline (no preamble, no markdown fences):
{{
    "thesis": "The core argument",
    "hook": "Opening that grabs attention",
    "framework": "Explanatory metaphor or thesis framework",
    "audience_framing": "{target_audience}",
    "total_target_words": {target_words},
    "sections": [
        {{
            "phase": "1",
            "name": "Section name",
            "target_words": 800,
            "key_points": ["point1", "point2"],
            "instructions": "Specific writing instructions for this section. Include how to frame for the audience."
        }}
    ]
}}

Requirements:
1. Sum of section target_words must equal {target_words}
2. Each section has specific, detailed instructions referencing the audience framing
3. All content must be in English
4. Sections build argument logically
5. Expand source material themes with original analysis"""

            outline_text = self.provider.complete(
                [{"role": "user", "content": prompt}], max_tokens=3000
            ).strip()

            try:
                outline = json.loads(outline_text)
            except json.JSONDecodeError:
                if '```json' in outline_text:
                    outline = json.loads(outline_text.split('```json')[1].split('```')[0])
                elif '```' in outline_text:
                    outline = json.loads(outline_text.split('```')[1].split('```')[0])
                else:
                    raise ValueError("Could not parse outline JSON")

            logger.info(f"Outline generated: {len(outline.get('sections', []))} sections")
            return {'success': True, 'outline': outline}

        except Exception as e:
            logger.error(f"Outline generation error: {e}")
            return {'success': False, 'error': str(e)}

    def _generate_youtube_outline(
        self,
        title: str,
        source_material: str,
        analysis: dict,
        duration_minutes: int,
        target_words: int,
        style: str,
        viewer_description: str,
    ) -> dict:
        """Generate a timed, spoken-word outline for a YouTube script."""
        try:
            num_sections = {10: 6, 15: 7, 25: 10}.get(duration_minutes, 7)

            prompt = f"""Create a YouTube video script outline. The creator has a written article and wants to turn it into a {duration_minutes}-minute YouTube video.

Title: {title}
Video Duration: {duration_minutes} minutes (~{target_words} spoken words total)
Style: {style}
Target Viewer: {viewer_description if viewer_description else 'general audience'}

Article Themes: {', '.join(analysis['key_themes'])}
Core Argument: {analysis['main_argument']}

SCRIPT STRUCTURE ({num_sections} sections):
- Section 1: Hook (first 30–45 seconds) — grabs attention immediately
- Sections 2 to {num_sections - 1}: Main content — progressively build the argument
- Section {num_sections}: Outro + CTA — wrap up and tell viewers what to do next

Generate a JSON outline (no preamble, no markdown fences):
{{
    "thesis": "What this video argues or reveals",
    "hook": "Exact opening line or question to grab attention",
    "total_duration_minutes": {duration_minutes},
    "total_target_words": {target_words},
    "sections": [
        {{
            "phase": "1",
            "name": "Hook",
            "start_time": "0:00",
            "end_time": "0:45",
            "target_words": 120,
            "key_points": ["attention-grabbing opening", "tease the main payoff"],
            "instructions": "Open with a surprising fact, bold claim, or question from the article. Speak directly to the viewer as 'you'. No intro music mention, no 'welcome back' — just dive in."
        }}
    ]
}}

RULES:
1. All target_words must sum to {target_words}
2. Section timings must be sequential and add up to {duration_minutes} minutes
3. Instructions must be specific and reference the article's content
4. Style '{style}' should shape the instructions — {{'explainer': 'break down complex ideas clearly', 'commentary': 'give your take and opinions boldly', 'analysis': 'dig into the why behind the facts', 'personal_take': 'use personal voice and first-person perspective'}}.get('{style}', 'match the style')
5. The outro must include a CTA (like, subscribe, link in description)"""

            text = self.provider.complete(
                [{"role": "user", "content": prompt}], max_tokens=3000
            ).strip()

            try:
                outline = json.loads(text)
            except json.JSONDecodeError:
                if '```json' in text:
                    outline = json.loads(text.split('```json')[1].split('```')[0])
                elif '```' in text:
                    outline = json.loads(text.split('```')[1].split('```')[0])
                else:
                    raise ValueError("Could not parse outline JSON")

            logger.info(f"YouTube outline generated: {len(outline.get('sections', []))} sections")
            return {'success': True, 'outline': outline}

        except Exception as e:
            logger.error(f"YouTube outline error: {e}")
            return {'success': False, 'error': str(e)}

    def _assemble_script(self, title: str, sections_content: dict, outline: dict, duration_minutes: int) -> str:
        """Assemble a YouTube script with timing markers."""
        try:
            script_parts = [f"# {title}\n", f"*{duration_minutes}-minute YouTube script*\n", "---\n"]

            for section in outline.get('outline', outline).get('sections', []):
                section_name = section['name']
                start = section.get('start_time', '')
                end = section.get('end_time', '')
                timing = f" — {start}–{end}" if start and end else ""

                if section_name in sections_content:
                    script_parts.append(f"## [{section_name.upper()}{timing}]\n")
                    script_parts.append(sections_content[section_name])
                    script_parts.append("")

            return "\n\n".join(script_parts)
        except Exception as e:
            logger.error(f"Script assembly error: {e}")
            return ""

    def _generate_section_chunked(
        self,
        section: dict,
        section_num: int,
        total_sections: int,
        source_material: str,
        previous_sections: dict,
        outline: dict,
        tone: str,
        target_audience: str,
        stream_callback=None,
        is_youtube: bool = False,
    ) -> str:
        """
        Generate a section in 500-word chunks, then merge them.
        Each chunk knows what the previous chunk wrote to avoid repetition.
        """
        try:
            section_target = section['target_words']
            num_chunks = max(1, math.ceil(section_target / CHUNK_SIZE))
            words_per_chunk = math.ceil(section_target / num_chunks)

            previous_context = "\n\n".join([
                f"[{name}]: {content[:300]}..."
                for name, content in list(previous_sections.items())[-2:]
            ])

            chunks = []
            chunk_so_far = ""

            for chunk_num in range(1, num_chunks + 1):
                is_first = chunk_num == 1
                is_last = chunk_num == num_chunks

                # Build continuation context from previous chunks in this section
                prev_chunk_context = ""
                if chunks:
                    prev_chunk_context = f"\nPrevious chunk(s) of this section:\n{chunks[-1][-500:]}\n(Do NOT repeat any of the above. Continue seamlessly.)"

                position_instruction = ""
                if is_first:
                    position_instruction = "This is the OPENING chunk. Start the section directly — no preamble, no 'In this section...' meta-commentary."
                elif is_last:
                    position_instruction = "This is the CLOSING chunk. Bring the section to a natural conclusion that sets up the next section."
                else:
                    position_instruction = f"This is chunk {chunk_num} of {num_chunks}. Continue the argument, building on what came before."

                if is_youtube:
                    prompt = f"""Write exactly {words_per_chunk} words of a YouTube video script section. This is SPOKEN WORD — the creator will read this directly on camera.

SECTION: {section['name']} (Phase {section.get('phase', section_num)})
Timing: {section.get('start_time', '')}–{section.get('end_time', '')}
Key points: {json.dumps(section['key_points'])}
Instructions: {section['instructions']}

VIEWER: {target_audience if target_audience else 'general audience'}
STYLE: {tone} — adapt accordingly

SOURCE ARTICLE (reference only — draw from it, don't quote it directly unless impactful):
{source_material[:1500]}

PRIOR SCRIPT SECTIONS (do NOT repeat):
{previous_context}
{prev_chunk_context}

POSITION: {position_instruction}

STRICT RULES:
- Write EXACTLY {words_per_chunk} words (±40 word tolerance)
- SPOKEN WORD only: use contractions ("it's", "don't", "here's"), direct address ("you", "we"), natural transitions ("So...", "Now here's the thing...", "But wait —")
- No academic language, no formal essay structure
- No section headers or labels inside the text
- No meta-commentary ("In this section...", "Let me explain...")
- If this is the Hook: start with the strongest possible opening line — a question, fact, or claim
- If this is the Outro: end with a clear CTA (like, subscribe, link in description)
- Flows naturally when read aloud

Write now:"""
                else:
                    prompt = f"""Write exactly {words_per_chunk} words of a professional English essay section.

SECTION: {section['name']} (Phase {section.get('phase', section_num)})
Key points: {json.dumps(section['key_points'])}
Instructions: {section['instructions']}

AUDIENCE & FRAMING:
Frame all arguments for: {target_audience}
Adapt examples, references, and argument style to resonate with this specific audience.

TONE: {tone}
LANGUAGE: English only. Do not use any other language.

SOURCE MATERIAL (reference only):
{source_material[:1500]}

PRIOR ESSAY SECTIONS (do NOT repeat):
{previous_context}
{prev_chunk_context}

POSITION: {position_instruction}

STRICT RULES:
- Write EXACTLY {words_per_chunk} words (±50 word tolerance)
- English only
- No section headers or titles inside the text
- No meta-commentary ("In this section...", "As we can see...")
- Support claims with evidence or examples relevant to the audience
- Natural prose that flows directly into the next chunk

Write now:"""

                chunk_content = ""

                chunk_content = self.provider.stream_complete(
                    [{"role": "user", "content": prompt}],
                    max_tokens=900,
                    on_token=lambda t: stream_callback('section_stream', t) if stream_callback else None,
                )

                chunk_content = chunk_content.strip()
                chunks.append(chunk_content)

                logger.info(f"Section {section_num} chunk {chunk_num}/{num_chunks}: {len(chunk_content.split())} words")

            # Merge all chunks with a single space (they are flowing prose)
            merged = " ".join(chunks)
            return merged

        except Exception as e:
            logger.error(f"Chunked section generation error: {e}")
            return None

    def _assemble_essay(self, title: str, sections_content: dict, outline: dict) -> str:
        try:
            essay_parts = [f"# {title}\n"]

            for section in outline.get('outline', outline).get('sections', []):
                section_name = section['name']
                if section_name in sections_content:
                    essay_parts.append(f"## {section_name}\n")
                    essay_parts.append(sections_content[section_name])
                    essay_parts.append("")

            full_essay = "\n\n".join(essay_parts)
            logger.info(f"Essay assembled: {len(full_essay.split())} total words")
            return full_essay

        except Exception as e:
            logger.error(f"Essay assembly error: {e}")
            return ""
