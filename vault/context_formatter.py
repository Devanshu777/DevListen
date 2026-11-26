"""
Shared HTML formatter for TemporalDecisionGraph entity context cards.
"""
import html
from typing import Any, Dict


def format_context_html(ctx: Dict[str, Any]) -> str:
    """Formats an entity's current truth and superseded history into HTML for the HUD."""
    entity = html.escape(str(ctx.get("entity", "Entity")))
    curr = ctx.get("current_decision")
    history = ctx.get("historical_decisions", [])

    if not curr and not history:
        return (
            f"<div style='color: #ECEFF1; font-size: 11px;'>"
            f"No recorded decisions found for <b>{entity}</b>.</div>"
        )

    parts = [
        "<div style='font-family: sans-serif; font-size: 11px;'>",
        f"<div style='color: #818CF8; font-weight: bold; font-size: 12px; margin-bottom: 4px;'>{entity}</div>",
    ]

    if curr:
        status = html.escape(str(curr.get("status", "ACTIVE")))
        summary = html.escape(str(curr.get("summary", "")))
        parts.append(
            f"""
        <div style='color: #10B981; font-weight: bold; margin-bottom: 2px;'>
            • CURRENT TRUTH [{status}]:
        </div>
        <div style='color: #F1F5F9; margin-left: 8px; margin-bottom: 6px;'>
            {summary}
        </div>
        """
        )

    if history:
        parts.append("<div style='color: #94A3B8; font-weight: bold; margin-top: 4px;'>• PRIOR HISTORY:</div>")
        for h in history:
            h_summary = html.escape(str(h.get("summary", "")))
            parts.append(
                f"""
            <div style='color: #64748B; font-size: 10px; margin-left: 8px;'>
                <s>{h_summary}</s> <span style='color: #F43F5E;'>[SUPERSEDED]</span>
            </div>
            """
            )

    parts.append("</div>")
    return "".join(parts)
