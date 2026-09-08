"""Audit trail for underwriting assumptions.

Underwriting assumptions change, and the reason a deal looked good in March is
often that somebody quietly moved the ARV. Every change to a material
assumption is recorded with its previous value, its new value, who made it,
when, and why if a reason was supplied.

The audit table is append-only by convention: nothing in the API updates or
deletes a row here.
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from ..auth import CurrentUser
from ..models import ActivityLog, AssumptionAudit, DealAnalysis

logger = logging.getLogger("atlas.audit")

# The assumptions material enough that a change to them must be recorded.
# Paths are dotted routes into the stored inputs JSON.
AUDITED_FIELDS: List[Tuple[str, str]] = [
    ("purchase_price", "Purchase price"),
    ("arv", "ARV"),
    ("arv_low", "ARV (low)"),
    ("arv_high", "ARV (high)"),
    ("rehab", "Rehab"),
    ("rehab_low", "Rehab (low)"),
    ("rehab_high", "Rehab (high)"),
    ("monthly_rent", "Monthly rent"),
    ("assumptions.flip.rehab_contingency", "Rehab contingency"),
    ("assumptions.flip.holding_months", "Holding period (months)"),
    ("assumptions.flip.minimum_net_profit", "Minimum flip profit"),
    ("assumptions.flip.minimum_roi", "Minimum flip ROI"),
    ("assumptions.flip.financing.loan_to_purchase", "Flip loan-to-purchase"),
    ("assumptions.flip.financing.annual_interest_rate", "Flip interest rate"),
    ("assumptions.flip.financing.points", "Flip loan points"),
    ("assumptions.rental.vacancy_percent", "Vacancy"),
    ("assumptions.rental.management_percent", "Management"),
    ("assumptions.rental.maintenance_percent", "Maintenance"),
    ("assumptions.rental.capex_percent", "CapEx"),
    ("assumptions.rental.annual_taxes", "Property taxes"),
    ("assumptions.rental.annual_insurance", "Insurance"),
    ("assumptions.rental.monthly_hoa", "HOA"),
    ("assumptions.rental.financing.loan_to_purchase", "Rental loan-to-purchase"),
    ("assumptions.rental.financing.annual_interest_rate", "Rental interest rate"),
    ("assumptions.transaction.purchase_closing_percent", "Purchase closing costs"),
    ("assumptions.transaction.sale_commission_percent", "Sale commission"),
    ("assumptions.transaction.sale_closing_percent", "Sale closing costs"),
    ("assumptions.holding.annual_taxes", "Holding period taxes"),
    ("assumptions.holding.annual_insurance", "Holding period insurance"),
    ("assumptions.wholesale.target_assignment_fee", "Target assignment fee"),
    ("assumptions.wholesale.buyer_profit_percent_of_arv", "Buyer profit target"),
    ("assumptions.brrrr.refinance_ltv", "Refinance LTV"),
    ("assumptions.brrrr.max_cash_left_in_deal", "Maximum cash left in deal"),
    ("assumptions.seller_finance.down_payment_percent", "Seller finance down payment"),
    ("assumptions.seller_finance.annual_interest_rate", "Seller finance rate"),
]


def _get_path(data: Optional[Dict[str, Any]], path: str) -> Any:
    node: Any = data or {}
    for part in path.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def _equivalent(old: Any, new: Any) -> bool:
    """Compare values without reporting a change that is only formatting.

    ``"0.15"`` and ``"0.150000"`` are the same assumption, and recording that as
    an edit would bury real changes in noise.
    """
    if old is None and new is None:
        return True
    if old is None or new is None:
        return False
    try:
        return Decimal(str(old)) == Decimal(str(new))
    except (InvalidOperation, ValueError):
        return str(old) == str(new)


def diff_assumptions(
    previous: Optional[Dict[str, Any]], current: Optional[Dict[str, Any]]
) -> List[Dict[str, Optional[str]]]:
    """Material assumption changes between two stored input payloads."""
    changes: List[Dict[str, Optional[str]]] = []
    for path, label in AUDITED_FIELDS:
        old = _get_path(previous, path)
        new = _get_path(current, path)
        if _equivalent(old, new):
            continue
        changes.append(
            {
                "field_path": path,
                "field_label": label,
                "previous_value": None if old is None else str(old)[:200],
                "new_value": None if new is None else str(new)[:200],
            }
        )
    return changes


def record_assumption_changes(
    db: Session,
    analysis: DealAnalysis,
    user: CurrentUser,
    previous_inputs: Optional[Dict[str, Any]],
    current_inputs: Optional[Dict[str, Any]],
    reason: Optional[str] = None,
) -> List[AssumptionAudit]:
    """Write one audit row per changed assumption."""
    changes = diff_assumptions(previous_inputs, current_inputs)
    entries: List[AssumptionAudit] = []
    for change in changes:
        entry = AssumptionAudit(
            analysis_id=analysis.id,
            property_id=analysis.property_id,
            changed_by=user.id,
            changed_by_email=user.email,
            field_path=change["field_path"],
            field_label=change["field_label"],
            previous_value=change["previous_value"],
            new_value=change["new_value"],
            reason=reason,
        )
        db.add(entry)
        entries.append(entry)
    if entries:
        logger.info(
            "analysis %s: %d assumption(s) changed by %s", analysis.id, len(entries), user.id
        )
    return entries


def log_activity(
    db: Session,
    user: Optional[CurrentUser],
    action: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[uuid.UUID] = None,
    summary: Optional[str] = None,
) -> ActivityLog:
    """Record an important action.

    Deliberately records what happened and to which record — never the contents
    of the record itself.
    """
    entry = ActivityLog(
        actor_id=user.id if user else None,
        actor_email=user.email if user else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=(summary or "")[:500] or None,
    )
    db.add(entry)
    logger.info("activity: %s %s %s", action, entity_type or "", entity_id or "")
    return entry
