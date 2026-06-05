"""
features/dedup.py
Deduplication Engine (v14)
Prevents two teachers from receiving the same script.
Uses both content hashing (exact) and semantic hashing (near-duplicate).
"""

import hashlib
import re
import logging

logger = logging.getLogger(__name__)


class Dedup:
    """
    Two-layer deduplication:
    - Content hash  : MD5 of first 500 chars — catches exact duplicates
    - Semantic hash : SHA256 of normalized text — catches near-duplicates
    """

    def __init__(self):
        self.content_hashes: set[str] = set()
        self.semantic_hashes: set[str] = set()

    def get_content_hash(self, text: str) -> str:
        """MD5 of first 500 characters."""
        return hashlib.md5(text[:500].encode()).hexdigest()

    def get_semantic_hash(self, text: str) -> str:
        """SHA256 of whitespace-normalized lowercase text (first 1000 chars)."""
        normalized = re.sub(r'\s+', ' ', text.lower())[:1000]
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]

    def is_duplicate(self, text: str) -> bool:
        """Return True if content or semantic duplicate already exists."""
        c_hash = self.get_content_hash(text)
        s_hash = self.get_semantic_hash(text)
        return c_hash in self.content_hashes or s_hash in self.semantic_hashes

    def register(self, text: str) -> tuple[str, str]:
        """Register a new script's hashes. Returns (content_hash, semantic_hash)."""
        c_hash = self.get_content_hash(text)
        s_hash = self.get_semantic_hash(text)
        self.content_hashes.add(c_hash)
        self.semantic_hashes.add(s_hash)
        logger.debug(f"Registered script hashes: c={c_hash[:8]} s={s_hash[:8]}")
        return c_hash, s_hash

    def check_and_register(self, text: str) -> bool:
        """
        Convenience method: check for duplicate, register if not.
        Returns True if it was a duplicate (i.e. script was NOT registered).
        """
        if self.is_duplicate(text):
            logger.warning("Duplicate script detected — skipping registration")
            return True
        self.register(text)
        return False

    @property
    def stats(self) -> dict:
        return {
            'unique_scripts': len(self.content_hashes),
            'semantic_fingerprints': len(self.semantic_hashes),
        }


# Module-level singleton shared across all requests
DEDUP = Dedup()
