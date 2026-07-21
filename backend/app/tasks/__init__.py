"""Celery task modules for background processing."""
from app.tasks.drawings import process_drawing
from app.tasks.ai_drawings import process_drawing_ai
from app.tasks.exports import (
    generate_export,
    generate_boq_xlsx,
    generate_proposal_pdf,
    generate_purchase_list,
    generate_client_presentation,
)
from app.tasks.quantities import compute_quantities

__all__ = [
    "process_drawing",
    "process_drawing_ai",
    "compute_quantities",
    "generate_export",
    "generate_boq_xlsx",
    "generate_proposal_pdf",
    "generate_purchase_list",
    "generate_client_presentation",
]

