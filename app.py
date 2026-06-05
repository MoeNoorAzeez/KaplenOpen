#!/usr/bin/env python3
"""
app.py — Kaplen Content Generation Platform
Pure orchestrator. Does three things only:
  1. Instantiate infrastructure (LLM provider, S3, DB)
  2. Wire all feature classes
  3. Register all routes via api_endpoints.register_all_routes()
"""

import os
import logging

import boto3
from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv

from config import get_config

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ============================================================================
# APP + CONFIG
# ============================================================================

config = get_config()

app = Flask(__name__)
app.config.from_object(config)
CORS(app)

# ============================================================================
# INFRASTRUCTURE
# ============================================================================

from features.llm_provider import get_provider

llm_provider = get_provider()
s3_client    = boto3.client(
    's3',
    region_name=config.AWS_REGION,
    aws_access_key_id=config.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=config.AWS_SECRET_ACCESS_KEY,
)

BUCKET = config.S3_BUCKET

# ============================================================================
# FEATURE WIRING
# Layer 0 → Layer 1 → Layer 2
# ============================================================================

from features.database           import DB
from features.dedup              import Dedup
from features.data_loader        import DataLoader
from features.curriculum_loader  import CurriculumRegistry, CurriculumLoader
from features.callaway           import CallawayFramework
from features.youtube_packager   import YoutubePackager
from features.validator          import ContentValidator
from features.script_store       import ScriptStore
from features.yt_analytics       import YtAnalyticsStore
from features.metrics            import MetricsEngine
from features.script_generator   import ScriptGenerator
from features.study_tips         import StudyTipsGenerator
from features.docx_export        import DocxExporter

# Layer 0
db    = DB()
dedup = Dedup()

# Layer 1
curriculum_registry = CurriculumRegistry(config.CURRICULUM_REGISTRY_PATH)
curriculum_loader   = CurriculumLoader(curriculum_registry, s3_client)
data_loader         = DataLoader(s3_client, BUCKET)
callaway            = CallawayFramework(llm_provider)
packager            = YoutubePackager(llm_provider)
validator           = ContentValidator(llm_provider)
script_store        = ScriptStore(db)
yt_store            = YtAnalyticsStore(db)
metrics             = MetricsEngine(db)

# Layer 2
scripts_cache: dict = {}  # {script_id: script_data} — session-scoped

script_generator     = ScriptGenerator(
    llm_provider, data_loader, callaway, packager, validator, dedup,
    metrics=metrics, curriculum_loader=curriculum_loader,
)
study_tips_generator = StudyTipsGenerator(llm_provider, callaway, packager, dedup)
docx_exporter        = DocxExporter(script_store, scripts_cache)

# ============================================================================
# DB INIT
# ============================================================================

db.init_tables()

# ============================================================================
# ROUTE REGISTRATION
# ============================================================================

from api_endpoints import register_all_routes

register_all_routes(
    app,
    data_loader          = data_loader,
    curriculum_registry  = curriculum_registry,
    curriculum_loader    = curriculum_loader,
    script_generator     = script_generator,
    study_tips_generator = study_tips_generator,
    script_store         = script_store,
    yt_store             = yt_store,
    metrics              = metrics,
    docx_exporter        = docx_exporter,
    scripts_cache        = scripts_cache,
    llm_provider         = llm_provider,
    validator            = validator,
    dedup                = dedup,
    s3_client            = s3_client,
    bucket               = BUCKET,
    config               = config,
)

# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == '__main__':
    logger.info("Starting Kaplen Content Generation Platform")
    logger.info(f"LLM    : {llm_provider.model_name}")
    logger.info(f"Bucket : {BUCKET}")
    logger.info(f"DB     : {db.database} @ {db.host}")
    app.run(host='0.0.0.0', port=5000, debug=config.FLASK_ENV == 'development')
