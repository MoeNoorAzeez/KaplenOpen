"""
features/podcast_generator.py
Podcast Outline Generator
Generates structured, guest-adapted podcast episode frameworks.
Structure-first, content-later: phases, segments, question patterns — not scripts.
Gated by active subscription (require_active_subscription).
"""

import json
import logging
import os
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)

_TZ_NAME = os.getenv('TIMEZONE', 'UTC')
APP_TZ = pytz.timezone(_TZ_NAME) if _TZ_NAME != 'UTC' else pytz.utc

# Default phase durations in seconds
PHASE_DEFAULTS = {
    'opening':       120,
    'credibility':   180,
    'process':       600,
    'philosophy':    600,
    'vulnerability': 420,
    'closing':       180,
}

# Question type weights per phase (base, before profile adjustments)
PHASE_QUESTION_WEIGHTS = {
    'opening':       {'observational': 0.0, 'clarification': 0.0, 'philosophical': 0.0, 'pivot': 1.0, 'challenge': 0.0},
    'credibility':   {'observational': 0.7, 'clarification': 0.2, 'philosophical': 0.1, 'pivot': 0.0, 'challenge': 0.0},
    'process':       {'observational': 0.3, 'clarification': 0.5, 'philosophical': 0.1, 'pivot': 0.1, 'challenge': 0.0},
    'philosophy':    {'observational': 0.1, 'clarification': 0.2, 'philosophical': 0.6, 'pivot': 0.05, 'challenge': 0.05},
    'vulnerability': {'observational': 0.0, 'clarification': 0.1, 'philosophical': 0.4, 'pivot': 0.3, 'challenge': 0.2},
    'closing':       {'observational': 0.0, 'clarification': 0.0, 'philosophical': 0.4, 'pivot': 0.2, 'challenge': 0.4},
}


class PodcastOutlineGenerator:
    """
    Generates a structured podcast episode outline from speaker + guest profiles.
    Uses Claude to produce intelligent, adaptive phase/segment content.
    Does NOT generate a script — generates a map for natural conversation.
    """

    def __init__(self, provider):
        """
        Args:
            provider: features.llm_provider.LLMProvider instance
        """
        self.provider = provider

    def generate(
        self,
        speaker_profile: dict,
        guest_profile: dict,
        episode_context: dict,
    ) -> dict:
        """
        Generate a complete podcast episode outline.

        Args:
            speaker_profile: Dict matching SpeakerProfile spec
                Required keys: name, role, expertise, communicationStyle,
                               listeningStyle, preferredQuestionTypes
            guest_profile: Dict matching GuestProfile spec
                Required keys: name, knownFor, communicationStyle,
                               monologueTendency, preferredDepth
            episode_context: Dict matching EpisodeContext spec
                Required keys: duration_minutes, focusAreas
                Optional: episodeTheme, seasonContext, forceStructure

        Returns:
            Result dict with success=True and full outline,
            or success=False with error message.
        """
        try:
            duration_minutes = episode_context.get('duration_minutes', 60)
            total_seconds    = duration_minutes * 60

            logger.info(
                f"Generating podcast outline: {speaker_profile.get('name')} x "
                f"{guest_profile.get('name')}, {duration_minutes}min"
            )

            # ════════════════════════════════════════════════════════════════
            # STEP 1: DETERMINE ACTIVE PHASES
            # ════════════════════════════════════════════════════════════════

            active_phases = self._select_phases(guest_profile, episode_context)

            # ════════════════════════════════════════════════════════════════
            # STEP 2: ALLOCATE TIMING ACROSS PHASES
            # ════════════════════════════════════════════════════════════════

            timed_phases = self._allocate_timing(active_phases, total_seconds, guest_profile)

            # ════════════════════════════════════════════════════════════════
            # STEP 3: GENERATE OUTLINE VIA CLAUDE
            # ════════════════════════════════════════════════════════════════

            outline = self._generate_outline_with_claude(
                speaker_profile=speaker_profile,
                guest_profile=guest_profile,
                episode_context=episode_context,
                timed_phases=timed_phases,
            )

            if not outline.get('success'):
                return outline

            # ════════════════════════════════════════════════════════════════
            # STEP 4: ASSEMBLE FINAL RESULT
            # ════════════════════════════════════════════════════════════════

            return {
                'success':          True,
                'speaker_name':     speaker_profile.get('name'),
                'guest_name':       guest_profile.get('name'),
                'duration_minutes': duration_minutes,
                'episode_theme':    episode_context.get('episodeTheme', ''),
                'focus_areas':      episode_context.get('focusAreas', []),
                'active_phases':    [p['id'] for p in timed_phases],
                'outline':          outline['outline'],
                'generated_at':     datetime.now(APP_TZ).isoformat(),
            }

        except Exception as e:
            logger.error(f"Podcast outline generation error: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    # ────────────────────────────────────────────────────────────────────────
    # PHASE SELECTION
    # ────────────────────────────────────────────────────────────────────────

    def _select_phases(self, guest_profile: dict, episode_context: dict) -> list:
        """
        Determine which phases to include based on guest attributes and context.
        Always includes opening and closing.
        Returns ordered list of phase dicts.
        """
        comm_style    = guest_profile.get('communicationStyle', {})
        vulnerability = comm_style.get('vulnerability', 'moderate')
        force_struct  = episode_context.get('forceStructure', 'standard')
        duration_min  = episode_context.get('duration_minutes', 60)
        focus_areas   = episode_context.get('focusAreas', [])

        phases = []

        # Opening — always
        phases.append({'id': 'opening', 'name': 'Opening & Greeting'})

        # Credibility — always unless guest is completely unknown (no knownFor)
        if guest_profile.get('knownFor'):
            phases.append({'id': 'credibility', 'name': 'Credibility & Guest Validation'})

        # Process — skip only for very short episodes without storytelling focus
        skip_process = (
            duration_min < 45
            and 'storytelling' not in ' '.join(focus_areas).lower()
            and comm_style.get('storytellingStrength') == 'weak'
        )
        if not skip_process:
            phases.append({'id': 'process', 'name': 'Craft & Process Deep Dive'})

        # Philosophy — skip if guest is low-vulnerability
        if vulnerability in ('moderate', 'high'):
            phases.append({'id': 'philosophy', 'name': 'Philosophy & Values'})

        # Vulnerability — skip if guest is low-vulnerability or host is silence-uncomfortable
        silence_comfort = episode_context.get('speaker', {}).get(
            'communicationStyle', {}
        ).get('silenceComfort', 50)

        if vulnerability == 'high' and silence_comfort >= 40:
            phases.append({'id': 'vulnerability', 'name': 'Deeper Reflection & Personal Truth'})
        elif vulnerability == 'moderate' and guest_profile.get('deepTouches'):
            phases.append({'id': 'vulnerability', 'name': 'Deeper Reflection & Personal Truth'})

        # Closing — always
        phases.append({'id': 'closing', 'name': 'Synthesis & Closing'})

        return phases

    # ────────────────────────────────────────────────────────────────────────
    # TIMING ALLOCATION
    # ────────────────────────────────────────────────────────────────────────

    def _allocate_timing(
        self,
        phases: list,
        total_seconds: int,
        guest_profile: dict,
    ) -> list:
        """
        Distribute total episode duration across active phases.
        Applies guest-attribute weighting multipliers before scaling.
        Returns phases list with targetDurationSeconds added.
        """
        comm_style    = guest_profile.get('communicationStyle', {})
        vulnerability = comm_style.get('vulnerability', 'moderate')
        monologue     = guest_profile.get('monologueTendency', 'medium')
        storytelling  = comm_style.get('storytellingStrength', 'moderate')

        # Vulnerability multipliers per phase
        vuln_mult = {
            'high':     {'philosophy': 1.3, 'vulnerability': 1.4, 'process': 0.8},
            'moderate': {'philosophy': 1.0, 'vulnerability': 1.0, 'process': 1.0},
            'low':      {'philosophy': 0.7, 'vulnerability': 0.4, 'process': 1.2},
        }.get(vulnerability, {})

        # Storytelling multiplier on process
        story_mult = {'exceptional': 1.5, 'moderate': 1.0, 'weak': 0.6}.get(storytelling, 1.0)

        # Monologue multiplier on process
        mono_mult = {'long': 1.3, 'medium': 1.0, 'short': 0.7}.get(monologue, 1.0)

        # Build weighted baseline
        weighted = []
        for phase in phases:
            pid      = phase['id']
            baseline = PHASE_DEFAULTS.get(pid, 300)

            mult = 1.0
            if pid in vuln_mult:
                mult *= vuln_mult[pid]
            if pid == 'process':
                mult *= story_mult * mono_mult

            weighted.append({**phase, 'weight': baseline * mult})

        baseline_total = sum(p['weight'] for p in weighted)
        scale          = total_seconds / max(baseline_total, 1)

        # Floor / ceiling bounds (seconds)
        bounds = {
            'opening':       (60,   300),
            'credibility':   (120,  480),
            'process':       (300, 1200),
            'philosophy':    (300, 1200),
            'vulnerability': (180,  900),
            'closing':       (120,  360),
        }

        timed = []
        for phase in weighted:
            pid = phase['id']
            raw = phase['weight'] * scale
            lo, hi = bounds.get(pid, (120, 1200))
            timed.append({
                **phase,
                'targetDurationSeconds': max(lo, min(hi, int(raw))),
                'flexibilityRange':      [lo, hi],
            })

        # Redistribute slack/overflow to phases with room
        allocated   = sum(p['targetDurationSeconds'] for p in timed)
        remaining   = total_seconds - allocated

        if remaining > 0:
            for phase in timed:
                if remaining <= 0:
                    break
                pid     = phase['id']
                lo, hi  = bounds.get(pid, (120, 1200))
                add     = min(remaining, hi - phase['targetDurationSeconds'])
                if add > 0:
                    phase['targetDurationSeconds'] += add
                    remaining -= add

        return timed

    # ────────────────────────────────────────────────────────────────────────
    # CLAUDE OUTLINE GENERATION
    # ────────────────────────────────────────────────────────────────────────

    def _generate_outline_with_claude(
        self,
        speaker_profile: dict,
        guest_profile:   dict,
        episode_context: dict,
        timed_phases:    list,
    ) -> dict:
        """
        Send profiles + computed phase structure to Claude.
        Claude returns a fully-fleshed podcast outline as JSON.
        """
        try:
            comm_style  = guest_profile.get('communicationStyle', {})
            focus_areas = episode_context.get('focusAreas', [])
            theme       = episode_context.get('episodeTheme', 'Not specified')
            duration    = episode_context.get('duration_minutes', 60)

            # Build phase summary for the prompt
            phase_summary = []
            for p in timed_phases:
                mins = p['targetDurationSeconds'] // 60
                secs = p['targetDurationSeconds'] % 60
                phase_summary.append(
                    f"- {p['name']} ({p['id']}): {mins}m {secs}s | "
                    f"base_weights: {json.dumps(PHASE_QUESTION_WEIGHTS.get(p['id'], {}))}"
                )
            phase_block = '\n'.join(phase_summary)

            prompt = f"""You are an expert podcast producer. Generate a complete, structured podcast episode outline as JSON.

EPISODE CONTEXT
- Duration: {duration} minutes
- Theme: {theme}
- Focus areas: {', '.join(focus_areas) or 'Not specified'}

HOST PROFILE
- Name: {speaker_profile.get('name', 'Host')}
- Expertise: {', '.join(speaker_profile.get('expertise', []))}
- Listening style: {speaker_profile.get('listeningStyle', 'balanced')}
- Communication: {json.dumps(speaker_profile.get('communicationStyle', {}))}
- Preferred question types (weights 0-100): {json.dumps(speaker_profile.get('preferredQuestionTypes', {}))}

GUEST PROFILE
- Name: {guest_profile.get('name', 'Guest')}
- Known for: {', '.join(guest_profile.get('knownFor', []))}
- Credibility markers: {json.dumps(guest_profile.get('credibilityMarkers', {}))}
- Communication style: {json.dumps(comm_style)}
- Monologue tendency: {guest_profile.get('monologueTendency', 'medium')}
- Preferred depth: {guest_profile.get('preferredDepth', 'moderate')}
- Response to silence: {guest_profile.get('responseToSilence', 'neutral')}
- Topics to avoid: {', '.join(guest_profile.get('avoidTopics', [])) or 'None'}
- Deep touch points: {', '.join(guest_profile.get('deepTouches', [])) or 'None'}
- Current phase: {guest_profile.get('currentPhase', 'Not specified')}
- Recent events: {', '.join(guest_profile.get('recentEvents', [])) or 'None'}

PHASE STRUCTURE (pre-computed timing, DO NOT change sequence or IDs)
{phase_block}

INSTRUCTIONS
Generate a podcast outline JSON. Follow these rules exactly:
1. Never write specific questions. Only generate question PATTERNS, types, and guidance.
2. The outline is a map, not a script. Hosts adapt in real time.
3. For each phase, generate segments (~3 minutes each = targetDurationSeconds / 180, rounded up).
4. Each segment gets: segmentType, questionPattern, topicArea, guidanceForHost.
5. Adjust question type weights using the host's preferredQuestionTypes (divide each by 50 to normalize, multiply by base_weight, then re-normalize).
6. Apply guest vulnerability adjustments: high -> expand philosophy/vulnerability, low -> compress them.
7. Include hostGuidance, adaptationRules, and researchNotes in the output.
8. All text must be in English.

Return ONLY valid JSON in this exact structure:
{{
  "metadata": {{
    "episodeId": "ep_<timestamp>",
    "speakerId": "{speaker_profile.get('name', 'host').lower().replace(' ', '_')}",
    "guestId": "{guest_profile.get('name', 'guest').lower().replace(' ', '_')}",
    "totalDuration": {duration * 60},
    "generatedAt": "{datetime.now(APP_TZ).isoformat()}"
  }},
  "summary": {{
    "episodeTheme": "<string>",
    "focusAreas": ["<string>"],
    "expectedTone": "<string>",
    "structuralStrategy": "<standard|debate|deepdive|rapid-fire>"
  }},
  "phases": [
    {{
      "id": "<phase_id>",
      "name": "<phase_name>",
      "sequence": <int>,
      "targetDurationSeconds": <int>,
      "primaryFunction": "<string>",
      "vulnerability": <0-100>,
      "guestMonologueLengthTarget": <seconds>,
      "questionMix": {{
        "observational": <0-1>,
        "clarification": <0-1>,
        "philosophical": <0-1>,
        "pivot": <0-1>,
        "challenge": <0-1>
      }},
      "contentAreas": [
        {{
          "topic": "<string>",
          "depthLevel": "surface|moderate|deep",
          "emotionalIntensity": "low|moderate|high"
        }}
      ],
      "segments": [
        {{
          "id": "seg_<phase_id>_<n>",
          "segmentType": "intro|main|pivot|deepdive|synthesis",
          "questionPattern": {{
            "type": "observational|clarification|philosophical|pivot|challenge",
            "affirmationRequired": <bool>,
            "followUpCount": <int>,
            "expectedMonologue": <seconds>
          }},
          "topicArea": "<string>",
          "adaptations": {{
            "ifHighVulnerability": {{ "slowDown": <bool>, "addSilence": <bool>, "reduceChallenges": <bool> }},
            "ifShortMonologues": {{ "addFollowUps": <int>, "reduceComplexity": <bool> }},
            "ifHighExpertise": {{ "increaseChallenge": <bool>, "allowDebate": <bool> }}
          }},
          "guidanceForHost": {{
            "tone": "<string>",
            "pacing": "rapid|measured|reflective",
            "interruptionStrategy": "minimal|moderate|active",
            "questionStyle": "<string>",
            "silenceHandling": "embrace|gentle-prompt|move-on"
          }}
        }}
      ],
      "transitionToNext": {{
        "strategy": "<string>",
        "bridgeLanguage": "<string>",
        "triggerPoints": ["<string>"]
      }}
    }}
  ],
  "hostGuidance": {{
    "communication": {{
      "affirmationApproach": "<string>",
      "silenceThreshold": <seconds>,
      "interruptionApproach": "<string>",
      "vulnerabilityMatching": "mirror|support|maintain"
    }},
    "pacing": {{
      "expectedRhythm": "<string>",
      "accelerationPoints": ["<string>"],
      "slowingPoints": ["<string>"]
    }},
    "contentFlow": {{
      "divergenceAllowance": "<string>",
      "returnToThemeStrategy": "<string>"
    }}
  }},
  "adaptationRules": {{
    "ifGuestShutDown": {{ "action": "<string>", "priority": 0 }},
    "ifGuestDominant": {{ "action": "<string>", "priority": 1 }},
    "ifTopicDivergence": {{ "action": "<string>", "priority": 2 }},
    "ifTimeConstraint": {{ "action": "<string>", "priority": 1 }},
    "ifUnexpectedEmotion": {{ "action": "<string>", "priority": 0 }}
  }},
  "researchNotes": {{
    "guestBackground": ["<string>"],
    "recentWork": ["<string>"],
    "suggestedReferences": ["<string>"],
    "potentialTangents": ["<string>"]
  }},
  "contentAnchors": {{
    "publications": ["<string>"],
    "channels": ["<string>"],
    "recentEvents": ["<string>"],
    "previousEpisodeCallbacks": ["<string>"]
  }}
}}"""

            raw = self.provider.complete(
                [{"role": "user", "content": prompt}], max_tokens=4000
            ).strip()

            # Safe JSON parse with fence stripping
            try:
                outline = json.loads(raw)
            except json.JSONDecodeError:
                if '```json' in raw:
                    outline = json.loads(raw.split('```json')[1].split('```')[0])
                elif '```' in raw:
                    outline = json.loads(raw.split('```')[1].split('```')[0])
                else:
                    raise ValueError("Could not parse outline JSON from Claude response")

            logger.info(
                f"Outline generated: {len(outline.get('phases', []))} phases, "
                f"theme: {outline.get('summary', {}).get('episodeTheme', 'N/A')}"
            )

            return {'success': True, 'outline': outline}

        except Exception as e:
            logger.error(f"Claude outline generation error: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}
