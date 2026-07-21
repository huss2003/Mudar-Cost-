"""Python enums used across all models as string-based enums."""

from enum import StrEnum


class ObjectType(StrEnum):
    WALL = "wall"
    FLOOR = "floor"
    CEILING = "ceiling"
    DOOR = "door"
    WINDOW = "window"
    PARTITION = "partition"
    STAIRCASE = "staircase"
    COLUMN = "column"
    BEAM = "beam"
    DUCT = "duct"
    PIPE = "pipe"
    CABLE_TRAY = "cable_tray"
    FURNITURE = "furniture"
    FIXTURE = "fixture"
    EQUIPMENT = "equipment"


class Unit(StrEnum):
    SQM = "sqm"
    SQF = "sqf"
    LNM = "lnm"
    LNF = "lnf"
    CUM = "cum"
    NOS = "nos"
    SET = "set"
    KG = "kg"
    LTR = "ltr"
    DAY = "day"
    POINT = "point"
    SHT = "sht"
    ROLL = "roll"
    BOX = "box"
    BAG = "bag"


class ProjectStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ESTIMATING = "estimating"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class DrawingStatus(StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    ANALYZED = "analyzed"
    FAILED = "failed"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVISION_REQUIRED = "revision_required"


class TradeType(StrEnum):
    CARPENTRY = "carpentry"
    ELECTRICAL = "electrical"
    PLUMBING = "plumbing"
    PAINTING = "painting"
    FLOORING = "flooring"
    CEILING = "ceiling"
    PARTITION = "partition"
    HVAC = "hvac"
    FIRE = "fire"
    DATA = "data"
    CIVIL = "civil"
    GLASS = "glass"
    STEEL = "steel"
    WATERPROOFING = "waterproofing"
