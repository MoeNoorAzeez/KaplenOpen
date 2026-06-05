"""
features/data_loader.py
S3 Data Loader — backward-compatible wrapper around CurriculumLoader.
Subjects, topics, subtopics, and curriculum content from S3.
"""

import json
import logging

logger = logging.getLogger(__name__)

# Subject map kept here for backward compatibility with routes that call
# get_subjects() directly without a curriculum_id.
SUBJECT_MAP = {
    'physics':          'physics',
    'chemistry':        'chemistry',
    'biology':          'bio',
    'arabic_language':  'arabic',
    'english_language': 'english',
    'mathematics':      'math',
    'general':          'general',
}


class DataLoader:
    """
    Load curriculum content from S3.
    Wraps CurriculumLoader when a curriculum_id is provided;
    falls back to legacy direct-S3 behavior for backward compatibility.
    """

    def __init__(self, s3_client, bucket: str, curriculum_loader=None):
        self.s3 = s3_client
        self.bucket = bucket
        self.curriculum_loader = curriculum_loader

    def get_subjects(self) -> list[str]:
        return list(SUBJECT_MAP.keys())

    def get_topics(self, subject: str, curriculum_id: str = None) -> list[str]:
        if curriculum_id and self.curriculum_loader:
            try:
                return self.curriculum_loader.get_children(
                    curriculum_id,
                    {self._first_level_name(curriculum_id): subject},
                    self._second_level_name(curriculum_id),
                )
            except Exception as e:
                logger.warning(f"CurriculumLoader fallback: {e}")

        try:
            s3_prefix = SUBJECT_MAP.get(subject, subject)
            response = self.s3.list_objects_v2(
                Bucket=self.bucket,
                Prefix=f'subtopics/{s3_prefix}/'
            )
            topics = set()
            for obj in response.get('Contents', []):
                parts = obj['Key'].split('/')
                if len(parts) >= 4 and parts[-1].endswith('.json'):
                    topics.add(parts[2])
            return sorted(topics)
        except Exception as e:
            logger.error(f"Error loading topics for {subject}: {e}")
            return []

    def get_subtopics(self, subject: str, topic: str, curriculum_id: str = None) -> list[str]:
        if curriculum_id and self.curriculum_loader:
            try:
                return self.curriculum_loader.get_children(
                    curriculum_id,
                    {self._first_level_name(curriculum_id): subject,
                     self._second_level_name(curriculum_id): topic},
                    self._third_level_name(curriculum_id),
                )
            except Exception as e:
                logger.warning(f"CurriculumLoader fallback: {e}")

        try:
            s3_prefix = SUBJECT_MAP.get(subject, subject)
            response = self.s3.list_objects_v2(
                Bucket=self.bucket,
                Prefix=f'subtopics/{s3_prefix}/{topic}/'
            )
            subtopics = []
            for obj in response.get('Contents', []):
                if obj['Key'].endswith('.json'):
                    subtopics.append(obj['Key'].split('/')[-1].replace('.json', ''))
            return sorted(subtopics)
        except Exception as e:
            logger.error(f"Error loading subtopics for {subject}/{topic}: {e}")
            return []

    def get_curriculum_content(self, subject: str, topic: str, subtopic: str,
                               curriculum_id: str = None) -> dict:
        if curriculum_id and self.curriculum_loader:
            try:
                levels = self._get_levels(curriculum_id)
                if len(levels) >= 3:
                    return self.curriculum_loader.get_content(
                        curriculum_id,
                        {levels[0]: subject, levels[1]: topic, levels[2]: subtopic}
                    )
            except Exception as e:
                logger.warning(f"CurriculumLoader fallback: {e}")

        try:
            s3_prefix = SUBJECT_MAP.get(subject, subject)
            key = f'subtopics/{s3_prefix}/{topic}/{subtopic}.json'
            response = self.s3.get_object(Bucket=self.bucket, Key=key)
            return json.loads(response['Body'].read().decode('utf-8'))
        except Exception as e:
            logger.error(f"Error loading curriculum for {subject}/{topic}/{subtopic}: {e}")
            return {}

    # ── private helpers ──────────────────────────────────────────────────────

    def _get_levels(self, curriculum_id: str) -> list[str]:
        if not self.curriculum_loader:
            return ['subject', 'topic', 'subtopic']
        curriculum = self.curriculum_loader.registry.get_curriculum(curriculum_id)
        if curriculum:
            return curriculum.get('structure', {}).get('levels', ['subject', 'topic', 'subtopic'])
        return ['subject', 'topic', 'subtopic']

    def _first_level_name(self, curriculum_id: str) -> str:
        return self._get_levels(curriculum_id)[0]

    def _second_level_name(self, curriculum_id: str) -> str:
        levels = self._get_levels(curriculum_id)
        return levels[1] if len(levels) > 1 else 'topic'

    def _third_level_name(self, curriculum_id: str) -> str:
        levels = self._get_levels(curriculum_id)
        return levels[2] if len(levels) > 2 else 'subtopic'
