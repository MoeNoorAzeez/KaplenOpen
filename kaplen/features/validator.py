"""
features/validator.py
Content Validation — Claude-powered curriculum coverage checking.
Quality rules and dimensions are pulled from the curriculum registry when available.
"""

import json
import re
import logging

logger = logging.getLogger(__name__)

DEFAULT_QUALITY_RULES = {
    'min_coverage_percentage': 70,
    'dimensions': ['accuracy', 'completeness', 'clarity', 'engagement', 'curriculum_alignment'],
}


class ContentValidator:

    def __init__(self, provider, curriculum_registry=None):
        self.provider = provider
        self.curriculum_registry = curriculum_registry

    def validate_coverage(
        self,
        script: str,
        curriculum_content: dict,
        subject: str,
        topic: str,
        curriculum_id: str = None,
    ) -> dict:
        """
        Validate curriculum coverage in a generated script.
        Quality rules are pulled from the curriculum registry if curriculum_id is given.

        Returns:
            {coverage_percentage, covered_concepts, missing_concepts, quality_assessment}
        """
        try:
            quality_rules = DEFAULT_QUALITY_RULES
            if curriculum_id and self.curriculum_registry:
                meta = self.curriculum_registry.get_curriculum(curriculum_id) or {}
                quality_rules = meta.get('metadata', {}).get('quality_rules', DEFAULT_QUALITY_RULES)

            curriculum_text = json.dumps(curriculum_content)[:2000]
            dimensions = ', '.join(quality_rules.get('dimensions', []))

            prompt = f"""You are a curriculum validation expert.

Subject: {subject}
Topic: {topic}
Quality dimensions to assess: {dimensions}

Curriculum content (truncated):
{curriculum_text}

Generated script (first 1000 chars):
{script[:1000]}

Determine what percentage of the curriculum content is covered in the script.

Return ONLY a JSON object:
{{
  "coverage_percentage": <0-100>,
  "covered_concepts": ["concept 1", "concept 2"],
  "missing_concepts": ["concept 1", "concept 2"],
  "quality_assessment": "brief assessment"
}}"""

            response_text = self.provider.complete(
                [{"role": "user", "content": prompt}], max_tokens=200
            ).strip()
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)

            if json_match:
                return json.loads(json_match.group())

            return {
                'coverage_percentage': 0,
                'covered_concepts': [],
                'missing_concepts': [],
                'quality_assessment': 'Validation parsing failed',
            }

        except Exception as e:
            logger.error(f"Validation error: {e}")
            return {
                'coverage_percentage': 0,
                'covered_concepts': [],
                'missing_concepts': [],
                'quality_assessment': 'Validation error',
            }
