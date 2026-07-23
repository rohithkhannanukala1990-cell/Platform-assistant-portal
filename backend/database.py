"""Compatibility shim. New code should import from backend.db.*"""

from backend.db.core import (  # noqa: F401
    DATABASE_URL,
    DEFAULT_SETTINGS,
    _column_exists,
    _import_models,
    _is_postgres,
    _is_sqlite,
    _migrate,
    _seed_rbac,
    _seed_settings,
    _seed_templates,
    _seed_tools,
    _seed_workspaces,
    create_db_and_tables,
    engine,
    get_db,
)
from backend.db.models import *  # noqa: F401,F403
from backend.db.repositories.incidents import *  # noqa: F401,F403
from backend.db.repositories.notifications import *  # noqa: F401,F403
from backend.db.repositories.webhooks import *  # noqa: F401,F403
from backend.db.repositories.settings import *  # noqa: F401,F403
from backend.db.repositories.tools import *  # noqa: F401,F403
