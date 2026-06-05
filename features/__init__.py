"""
features/__init__.py — Register implemented feature blueprints.
Stub blueprints (analytics, batch, timeline) are excluded until implemented.
"""

from .synthesis import synthesis_bp

FEATURES = {
    'synthesis': synthesis_bp,
}


def register_features(app):
    """Register all active feature blueprints with Flask app."""
    for feature_name, blueprint in FEATURES.items():
        app.register_blueprint(blueprint)
