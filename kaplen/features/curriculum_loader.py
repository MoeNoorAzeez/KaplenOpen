"""
features/curriculum_loader.py
Pluggable curriculum registry and S3-backed content loader.

CurriculumRegistry: loads and caches curricula/registry.json
CurriculumLoader:   fetches hierarchy and content from S3 using registry metadata
"""

import json
import os
import logging

logger = logging.getLogger(__name__)

_DEFAULT_REGISTRY_PATH = os.getenv('CURRICULUM_REGISTRY_PATH', 'curricula/registry.json')


class CurriculumRegistry:

    def __init__(self, registry_path: str = _DEFAULT_REGISTRY_PATH):
        self._path = registry_path
        self._registry = None

    def _load(self):
        if self._registry is None:
            try:
                with open(self._path, 'r', encoding='utf-8') as f:
                    self._registry = json.load(f)
            except FileNotFoundError:
                logger.warning(f"Registry not found at {self._path}, using empty registry")
                self._registry = {'curricula': {}}
            except Exception as e:
                logger.error(f"Failed to load curriculum registry: {e}")
                self._registry = {'curricula': {}}

    def get_curriculum(self, curriculum_id: str) -> dict | None:
        self._load()
        return self._registry['curricula'].get(curriculum_id)

    def list_curricula(self) -> list[str]:
        self._load()
        return list(self._registry['curricula'].keys())

    def get_all(self) -> dict:
        self._load()
        return self._registry['curricula']


class CurriculumLoader:

    def __init__(self, registry: CurriculumRegistry, s3_client):
        self.registry = registry
        self.s3 = s3_client

    def _resolve_bucket(self, curriculum: dict) -> str:
        """Resolve the S3 bucket: read from env var named in curriculum config."""
        env_var = curriculum.get('s3_bucket_env', 'S3_BUCKET')
        bucket = os.getenv(env_var)
        if not bucket:
            raise ValueError(f"S3 bucket env var '{env_var}' is not set")
        return bucket

    def get_hierarchy_level(self, curriculum_id: str, level_name: str) -> list[str]:
        """
        Return available items at the given level of the hierarchy.
        For the first level (e.g. 'subject') this returns the subject_map keys.
        For deeper levels, scans S3 with the appropriate prefix.
        """
        curriculum = self.registry.get_curriculum(curriculum_id)
        if not curriculum:
            logger.error(f"Unknown curriculum: {curriculum_id}")
            return []

        structure = curriculum.get('structure', {})
        levels = structure.get('levels', [])
        subject_map = structure.get('subject_map', {})

        if not levels:
            return []

        if level_name == levels[0]:
            return list(subject_map.keys()) if subject_map else []

        return []

    def get_children(self, curriculum_id: str, path_args: dict, child_level: str) -> list[str]:
        """
        Given path_args that describe the parent path, return children at child_level.
        E.g. path_args={subject: 'chemistry', topic: 'equilibrium'} → subtopics list
        """
        curriculum = self.registry.get_curriculum(curriculum_id)
        if not curriculum:
            return []

        structure = curriculum.get('structure', {})
        levels = structure.get('levels', [])
        subject_map = structure.get('subject_map', {})
        bucket = self._resolve_bucket(curriculum)

        child_idx = levels.index(child_level) if child_level in levels else -1
        if child_idx < 0:
            return []

        # Build S3 prefix from path_args up to the child level
        path_template = structure.get('path_template', '')
        # Replace known path args; use prefix scan for the child level
        prefix_parts = []
        for level in levels[:child_idx]:
            val = path_args.get(level, '')
            if level == levels[0]:
                val = subject_map.get(val, val)
            prefix_parts.append(val)

        prefix = '/'.join(prefix_parts)
        # Strip leaf filename from path_template to get folder structure
        folder_template = '/'.join(path_template.split('/')[:-1])
        folder_prefix = folder_template
        for level in levels[:-1]:
            placeholder = '{' + level + '}'
            val = path_args.get(level, '')
            if level == levels[0]:
                val = subject_map.get(val, val)
            folder_prefix = folder_prefix.replace(placeholder, val)

        try:
            response = self.s3.list_objects_v2(
                Bucket=bucket,
                Prefix=folder_prefix + '/'
            )
            items = set()
            for obj in response.get('Contents', []):
                parts = obj['Key'].split('/')
                idx = len(folder_prefix.split('/'))
                if len(parts) > idx:
                    item = parts[idx]
                    if child_level == levels[-1]:
                        item = item.replace('.json', '')
                    if item:
                        items.add(item)
            return sorted(items)
        except Exception as e:
            logger.error(f"S3 hierarchy scan error for {curriculum_id}/{child_level}: {e}")
            return []

    def get_content(self, curriculum_id: str, path_args: dict) -> dict:
        """
        Fetch and parse curriculum JSON from S3 using the curriculum's path_template.
        path_args keys must match the level names in the curriculum structure.
        """
        curriculum = self.registry.get_curriculum(curriculum_id)
        if not curriculum:
            logger.error(f"Unknown curriculum: {curriculum_id}")
            return {}

        structure = curriculum.get('structure', {})
        path_template = structure.get('path_template', '')
        subject_map = structure.get('subject_map', {})
        levels = structure.get('levels', [])
        bucket = self._resolve_bucket(curriculum)

        key = path_template
        for level in levels:
            placeholder = '{' + level + '}'
            val = path_args.get(level, '')
            if level == levels[0] and subject_map:
                val = subject_map.get(val, val)
            key = key.replace(placeholder, val)

        try:
            response = self.s3.get_object(Bucket=bucket, Key=key)
            return json.loads(response['Body'].read().decode('utf-8'))
        except Exception as e:
            logger.error(f"CurriculumLoader.get_content error ({curriculum_id}, {path_args}): {e}")
            return {}
