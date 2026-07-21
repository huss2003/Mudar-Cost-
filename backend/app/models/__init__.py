"""SQLAlchemy 2.0 models for Auto Cost Engine.

All model classes are imported here so Alembic's autogenerate can discover them.
"""
# Import Base for Alembic discovery
from app.database import Base  # noqa: F401

# Enums
from app.models.enums import (  # noqa: F401
    ApprovalStatus,
    DrawingStatus,
    ObjectType,
    ProjectStatus,
    TradeType,
    Unit,
)

# Mixins (included via class inheritance — not imported as standalone)

# Core
from app.models.core import Drawing, Project, User  # noqa: F401

# Detection & estimation
from app.models.detection import BOQItem, CostVersion, DetectedObject  # noqa: F401

# Reference & catalogue
from app.models.reference import (  # noqa: F401
    DrawingObjectType,
    LabourRate,
    Material,
    Vendor,
)

# Rules
from app.models.rules import BOQRule, CompanyStandard, ProductivityRate, WastageRule  # noqa: F401

# Assets & templates
from app.models.assets_templates import ClientTemplate, DesignAsset  # noqa: F401

# History & audit
from app.models.history import (  # noqa: F401
    ExportRecord,
    ProcurementHistory,
    Profitability,
    ProjectHistory,
    RateHistory,
    RevisionHistory,
)

# Failed jobs (Celery dead-letter capture)
from app.models.failed_job import FailedJob  # noqa: F401
