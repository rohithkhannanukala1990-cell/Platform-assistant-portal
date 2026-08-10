"""PDF export of a workflow run — for postmortems and audit evidence packs.

Scrubs the same secret-key-name heuristic used in
``artifact_service.propose_artifact`` before anything from a step's context
(inputs, outputs, args) is rendered into the document.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

_SECRET_KEY_MARKERS = ("token", "password", "secret", "api_key", "credential")


def _scrub(value: Any) -> Any:
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if any(m in str(k).lower() for m in _SECRET_KEY_MARKERS):
                continue
            out[k] = _scrub(v)
        return out
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    return value


def _duration_label(started_at: str | None, completed_at: str | None) -> str:
    if not started_at or not completed_at:
        return "—"
    try:
        start = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
        end = datetime.fromisoformat(str(completed_at).replace("Z", "+00:00"))
    except ValueError:
        return "—"
    seconds = max(0.0, (end - start).total_seconds())
    if seconds < 1:
        return f"{int(seconds * 1000)}ms"
    if seconds < 60:
        return f"{seconds:.1f}s"
    return f"{int(seconds // 60)}m {int(seconds % 60)}s"


def build_run_pdf(run: dict[str, Any], definition: dict[str, Any] | None) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, topMargin=0.6 * inch, bottomMargin=0.6 * inch)
    styles = getSampleStyleSheet()
    mono = ParagraphStyle("mono", parent=styles["Code"], fontSize=7, leading=9)
    body = styles["BodyText"]

    story: list[Any] = []
    name = (definition or {}).get("name") or run.get("workflow_id") or "Workflow run"
    story.append(Paragraph(f"Workflow run: {name}", styles["Title"]))
    story.append(Spacer(1, 6))

    meta_rows = [
        ["Run ID", run.get("id", "")],
        ["Workflow ID", run.get("workflow_id", "")],
        ["Status", run.get("status", "")],
        ["Grounding", run.get("grounding", "")],
        ["Dry run", "yes" if run.get("dry_run") else "no"],
        ["Started", run.get("started_at") or "—"],
        ["Completed", run.get("completed_at") or "—"],
        ["Triggered by", run.get("triggered_by") or "—"],
    ]
    if run.get("error"):
        meta_rows.append(["Error", run["error"]])
    meta_table = Table(meta_rows, colWidths=[1.5 * inch, 5 * inch])
    meta_table.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(meta_table)
    story.append(Spacer(1, 14))

    story.append(Paragraph("Steps", styles["Heading2"]))
    steps_state: dict[str, Any] = run.get("steps_state") or {}
    def_steps = (definition or {}).get("steps") or []
    step_order = [s.get("id") for s in def_steps] or list(steps_state.keys())

    header = ["Step", "Type", "Status", "Duration", "Grounding"]
    rows = [header]
    for sid in step_order:
        st = steps_state.get(sid) or {}
        rows.append(
            [
                sid,
                st.get("type", ""),
                st.get("status", "pending"),
                _duration_label(st.get("started_at"), st.get("completed_at")),
                st.get("grounding", "") or "—",
            ]
        )
    step_table = Table(rows, colWidths=[1.1 * inch, 1.1 * inch, 1.3 * inch, 1.1 * inch, 1.1 * inch])
    step_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(step_table)
    story.append(Spacer(1, 14))

    for sid in step_order:
        st = steps_state.get(sid) or {}
        story.append(Paragraph(f"Step {sid}", styles["Heading3"]))
        if st.get("prompt"):
            story.append(Paragraph(f"Prompt: {st['prompt']}", body))
        decided_by = st.get("approved_by") or st.get("rejected_by")
        if decided_by:
            decision = "Approved" if st.get("approved_by") else "Rejected"
            when = st.get("approved_at") or st.get("completed_at") or ""
            story.append(Paragraph(f"{decision} by {decided_by} at {when}", body))
            if st.get("reason"):
                story.append(Paragraph(f"Reason: {st['reason']}", body))
        output = _scrub(st.get("output"))
        if output:
            text = json.dumps(output, indent=2, default=str)[:4000]
            story.append(Paragraph(text.replace("\n", "<br/>").replace(" ", "&nbsp;"), mono))
        story.append(Spacer(1, 10))

    story.append(Spacer(1, 12))
    story.append(
        Paragraph(
            f"Generated {datetime.now(timezone.utc).isoformat()} — secrets scrubbed from all rendered fields.",
            ParagraphStyle("footer", parent=body, fontSize=7, textColor=colors.grey),
        )
    )

    doc.build(story)
    return buf.getvalue()
