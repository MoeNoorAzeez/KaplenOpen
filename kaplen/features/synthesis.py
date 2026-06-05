"""
Teacher Style Synthesis Feature - Streaming Edition
Stream analysis results as they complete instead of blocking
"""

from flask import Blueprint, jsonify, request, Response
import json
import csv
from pathlib import Path
from kaplen.features.llm_provider import get_provider as _get_provider
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)

synthesis_bp = Blueprint('synthesis', __name__, url_prefix='/api/teachers/synthesis')

_provider = _get_provider()


class StreamingSynthesizer:
    """Analyze transcripts and stream results as they complete"""
    
    def __init__(self, csv_file: str = None):
        self.csv_file = csv_file
        self.transcripts = {}
        
        if csv_file and Path(csv_file).exists():
            self.load_transcripts(csv_file)
    
    def load_transcripts(self, csv_file: str):
        """Load transcripts from CSV"""
        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    video_id = row.get('video_id')
                    subject = row.get('subject')
                    week = row.get('week')
                    
                    if not week:
                        continue
                    
                    key = f"{subject}_week{week}"
                    if key not in self.transcripts:
                        self.transcripts[key] = []
                    
                    self.transcripts[key].append({
                        'video_id': video_id,
                        'subject': subject,
                        'week': week,
                        'transcript': row.get('transcript', '')[:2000],
                        'playlist': row.get('playlist', '')
                    })
            
            logger.info(f"Loaded {len(self.transcripts)} week-subject groups")
            return True
        except Exception as e:
            logger.error(f"Error loading transcripts: {e}")
            return False
    
    def analyze_transcript_group(self, subject: str, week: int, transcripts: list) -> dict:
        """Analyze a group of transcripts"""
        
        combined = "\n---\n".join([
            f"Teacher ({t.get('playlist', 'Unknown')}):\n{t['transcript']}"
            for t in transcripts[:5]
        ])
        
        prompt = f"""أنت خبير في تحليل أساليب التدريس الفعالة.

لديك محاضرات من معلمين مختلفين يشرحون نفس الموضوع (الأسبوع {week} من {subject}):

{combined}

حلّل هذه المحاضرات واستخرج:

أرجع JSON بدون شرح:

{{
  "subject": "{subject}",
  "week": {week},
  "num_teachers": {len(transcripts)},
  "common_patterns": {{
    "opening_techniques": ["تقنية 1", "تقنية 2"],
    "key_analogies": ["تشبيه 1", "تشبيه 2"],
    "exam_emphasis": ["نقطة 1", "نقطة 2"],
    "engagement_hooks": ["حيلة 1", "حيلة 2"]
  }},
  "best_practices": "ملخص الممارسات الأفضل",
  "tone": "الطبع الموصى به",
  "recommended_pacing": "السرعة الموصى بها"
}}
"""
        
        try:
            import re
            text = _provider.complete(
                [{"role": "user", "content": prompt}], max_tokens=800
            )
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                return json.loads(match.group())
        except Exception as e:
            logger.error(f"Error analyzing transcripts: {e}")
        
        return None
    
    def synthesize_stream(self):
        """Stream synthesis results as they complete"""
        
        count = 0
        total = len(self.transcripts)
        
        for key, transcripts in self.transcripts.items():
            if len(transcripts) < 2:
                continue
            
            subject, week = key.replace('_week', ':').split(':')
            week = int(week)
            
            logger.info(f"Analyzing {subject} week {week} ({len(transcripts)} teachers)...")
            
            analysis = self.analyze_transcript_group(subject, week, transcripts)
            
            count += 1
            progress = {
                "status": "analyzing",
                "progress": f"{count}/{total}",
                "subject": subject,
                "week": week,
                "num_teachers": len(transcripts),
                "result": analysis,
                "timestamp": str(__import__('datetime').datetime.now())
            }
            
            yield json.dumps(progress) + "\n"

# ============================================================================
# API ENDPOINTS
# ============================================================================

@synthesis_bp.route('/health', methods=['GET'])
def health():
    """Health check"""
    return jsonify({
        "status": "ok",
        "service": "synthesis",
        "description": "Teacher style synthesis engine (streaming)"
    })


@synthesis_bp.route('/analyze-stream', methods=['POST'])
def analyze_stream():
    """
    Stream synthesis analysis
    
    POST body:
    {
        "csv_file": "path/to/transcripts.csv"
    }
    """
    try:
        data = request.json
        csv_file = data.get('csv_file', 'transcripts_20260310_065900_assigned_weeks.csv')
        
        # Load and analyze
        synthesizer = StreamingSynthesizer(csv_file)
        
        if not synthesizer.transcripts:
            return jsonify({
                "error": "No transcripts loaded",
                "csv_file": csv_file
            }), 400
        
        # Stream results
        return Response(
            synthesizer.synthesize_stream(),
            mimetype='application/x-ndjson',
            headers={'X-Content-Type-Options': 'nosniff'}
        )
    
    except Exception as e:
        logger.error(f"Error: {e}")
        return jsonify({"error": str(e)}), 500


@synthesis_bp.route('/status', methods=['GET'])
def status():
    """Get synthesis status"""
    return jsonify({
        "status": "operational",
        "service": "Teacher Style Synthesis (Streaming)",
        "capabilities": [
            "Stream analysis of multiple teacher transcripts",
            "Extract common teaching patterns in real-time",
            "Synthesize optimal teaching style",
            "Non-blocking async processing"
        ],
        "usage": {
            "stream": "POST /api/teachers/synthesis/analyze-stream (NDJSON)",
        }
    })
