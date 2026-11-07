"""HITL Dashboard for Baton.

Minimal FastAPI app exposing the Human-in-the-Loop approval dashboard.
Reads pending approvals from DB, allows approve/reject via POST endpoint.
"""

from typing import Any

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from core.db import get_conn

app = FastAPI(title="Baton HITL Dashboard")


class ApprovalResponse(BaseModel):
    """Response model for approval actions."""
    approval_id: str
    status: str
    approved_by: str | None = None
    notes: str | None = None
    
    
@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.get("/approvals", response_model=list[dict[str, Any]])
async def list_pending_approvals() -> list[dict[str, Any]]:
    """Return all approvals WHERE status = 'pending'."""
    async with get_conn() as conn:
        # FIXED: Added JOIN to leads table and extracted name from metadata JSONB
        rows = await conn.execute(
            """
            SELECT a.id, a.quotation_id, a.status, a.requested_at, a.resolved_at,
                   q.lead_id, q.total_amount, q.line_items, l.metadata->>'name' as lead_name
            FROM approvals a
            JOIN quotations q ON a.quotation_id = q.id
            JOIN leads l ON q.lead_id = l.id
            WHERE a.status = 'pending'
            ORDER BY a.requested_at ASC
            """
        )
        results = await rows.fetchall()

        approvals = []
        for row in results:
            approvals.append({
                "id": row[0],
                "quotation_id": row[1],
                "status": row[2],
                "requested_at": row[3].isoformat() if row[3] else None,
                "resolved_at": row[4].isoformat() if row[4] else None,
                "lead_id": row[5],
                "lead_name": row[8] or "Unknown Business", # <-- This is the fix!
                "total_amount": float(row[6]) if row[6] else 0.0,
                "line_items": row[7],
            })
        return approvals


@app.post("/approvals/{approval_id}/approve", response_model=ApprovalResponse)
async def approve(
    approval_id: str,
    approved_by: str = Query(..., description="User ID who approved"),
) -> ApprovalResponse:
    """UPDATE approvals SET status='approved', approved_by=..., resolved_at=NOW()."""
    async with get_conn() as conn:
        row = await conn.execute(
            "SELECT id FROM approvals WHERE id = %s AND status = 'pending'", (approval_id,)
        )
        existing = await row.fetchone()

        if not existing:
            raise HTTPException(status_code=404, detail="Pending approval not found")

        await conn.execute(
            """
            UPDATE approvals
            SET status = 'approved', approved_by = %s, resolved_at = NOW()
            WHERE id = %s
            """,
            (approved_by, approval_id),
        )

    return ApprovalResponse(
        approval_id=approval_id,
        status="approved",
        approved_by=approved_by,
    )


@app.post("/approvals/{approval_id}/reject", response_model=ApprovalResponse)
async def reject(
    approval_id: str,
    approved_by: str = Query(..., description="User ID who rejected"),
    notes: str = Query("", description="Optional rejection notes"),
) -> ApprovalResponse:
    """UPDATE approvals SET status='rejected', notes=..., resolved_at=NOW()."""
    async with get_conn() as conn:
        row = await conn.execute(
            "SELECT id FROM approvals WHERE id = %s AND status = 'pending'", (approval_id,)
        )
        existing = await row.fetchone()

        if not existing:
            raise HTTPException(status_code=404, detail="Pending approval not found")

        await conn.execute(
            """
            UPDATE approvals
            SET status = 'rejected', approved_by = %s, notes = %s, resolved_at = NOW()
            WHERE id = %s
            """,
            (approved_by, notes, approval_id),
        )

    return ApprovalResponse(
        approval_id=approval_id,
        status="rejected",
        approved_by=approved_by,
        notes=notes,
    )