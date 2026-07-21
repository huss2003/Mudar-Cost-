"""Re-export Base and all models for Alembic discovery and application imports.

This file is kept for backward compatibility.  All model definitions now live
in the ``app.models`` package; import from there for new code.
"""
from app.database import Base  # noqa: F401 — re-export for Alembic & imports
from app.models import (  # noqa: F401
    BOQItem,
    BOQRule,
    ClientTemplate,
    CompanyStandard,
    CostVersion,
    DesignAsset,
    DetectedObject,
    Drawing,
    DrawingObjectType,
    LabourRate,
    Material,
    ProcurementHistory,
    ProductivityRate,
    Profitability,
    Project,
    ProjectHistory,
    RateHistory,
    RevisionHistory,
    User,
    Vendor,
    WastageRule,
)
