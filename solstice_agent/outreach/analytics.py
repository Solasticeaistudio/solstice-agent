"""
Outreach Analytics
==================
Campaign learning and next-best-action prioritization.
"""

from datetime import datetime, timezone
from typing import List, Tuple

from .models import LeadStage
from .store import get_store


def outreach_analytics(campaign_id: str = "") -> str:
    store = get_store()
    leads = store.list_leads(campaign_id=campaign_id or None)
    if not leads:
        scope = f"campaign '{campaign_id}'" if campaign_id else "all campaigns"
        return f"No leads found for {scope}."

    total = len(leads)
    contacted = len([l for l in leads if l.emails_sent > 0])
    replied = len([l for l in leads if l.emails_received > 0])
    positive = len([l for l in leads if any(tag in l.tags for tag in ("engaged_positive", "needs_info", "demo_requested"))])
    demos = len([l for l in leads if "demo_requested" in l.tags])
    pricing = len([l for l in leads if "pricing_requested" in l.tags])
    deferred = len([l for l in leads if "deferred" in l.tags])
    objections = len([l for l in leads if "objection" in l.tags])
    routed = len([l for l in leads if "routed" in l.tags])
    opt_out = len([l for l in leads if l.opted_out or "opt_out" in l.tags])
    converted = len([l for l in leads if l.stage == LeadStage.CONVERTED])

    industry_rows = _industry_breakdown(leads)
    lines = [
        f"OUTREACH ANALYTICS ({'all campaigns' if not campaign_id else campaign_id})",
        f"  Leads: {total}",
        f"  Contacted: {contacted}",
        f"  Replied: {replied} ({_pct(replied, contacted)})",
        f"  Positive intent: {positive} ({_pct(positive, replied)})",
        f"  Demo requests: {demos}",
        f"  Pricing asks: {pricing}",
        f"  Deferred: {deferred}",
        f"  Routed: {routed}",
        f"  Objections: {objections}",
        f"  Opt-outs: {opt_out}",
        f"  Converted: {converted}",
        "",
        "Industry breakdown:",
    ]
    lines.extend(industry_rows)
    return "\n".join(lines)


def outreach_next_best_actions(campaign_id: str = "", limit: int = 10) -> str:
    store = get_store()
    leads = store.list_leads(campaign_id=campaign_id or None)
    if not leads:
        scope = f"campaign '{campaign_id}'" if campaign_id else "all campaigns"
        return f"No leads found for {scope}."

    ranked: List[Tuple[int, object, str]] = []
    now = datetime.now(timezone.utc)

    for lead in leads:
        score = 0
        reason = []

        if lead.stage == LeadStage.QUALIFIED and lead.emails_sent == 0:
            score += 90
            reason.append("ready_for_initial_outreach")
        if "demo_requested" in lead.tags:
            score += 120
            reason.append("demo_interest")
        if "pricing_requested" in lead.tags:
            score += 110
            reason.append("pricing_follow_up")
        if "needs_info" in lead.tags:
            score += 80
            reason.append("needs_information")
        if "objection" in lead.tags:
            score += 70
            reason.append("objection_to_address")
        if "routed" in lead.tags:
            score += 75
            reason.append("routed_internal")
        if lead.stage in (LeadStage.REPLIED, LeadStage.ENGAGED):
            score += 85
            reason.append("active_reply_state")
        if lead.deferred_until:
            try:
                deferred_at = datetime.fromisoformat(lead.deferred_until)
                if deferred_at <= now:
                    score += 60
                    reason.append("defer_window_reached")
                else:
                    score -= 40
                    reason.append("still_deferred")
            except ValueError:
                pass
        if lead.opted_out or lead.stage == LeadStage.LOST:
            score = -999
            reason = ["do_not_contact"]

        ranked.append((score, lead, ",".join(reason) or "general"))

    ranked.sort(key=lambda item: item[0], reverse=True)
    lines = [f"NEXT BEST ACTIONS ({min(len(ranked), max(limit, 0))} shown):"]
    for score, lead, reason in ranked[:max(limit, 0)]:
        if score < 0:
            continue
        lines.append(
            f"  {lead.first_name} {lead.last_name} ({lead.company})\n"
            f"    Score: {score}\n"
            f"    Stage: {lead.stage.value}\n"
            f"    Last intent: {lead.last_detected_intent or 'unknown'}\n"
            f"    Tags: {', '.join(lead.tags) or 'none'}\n"
            f"    Reason: {reason}\n"
            f"    Lead ID: {lead.id}"
        )
    return "\n".join(lines)


def _pct(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "N/A"
    return f"{(numerator / denominator) * 100:.1f}%"


def _industry_breakdown(leads) -> List[str]:
    grouped = {}
    for lead in leads:
        key = lead.industry or "Unknown"
        bucket = grouped.setdefault(key, {"total": 0, "replied": 0, "positive": 0, "demos": 0})
        bucket["total"] += 1
        if lead.emails_received > 0:
            bucket["replied"] += 1
        if any(tag in lead.tags for tag in ("engaged_positive", "needs_info", "demo_requested")):
            bucket["positive"] += 1
        if "demo_requested" in lead.tags:
            bucket["demos"] += 1

    rows = []
    for industry in sorted(grouped):
        bucket = grouped[industry]
        rows.append(
            f"  {industry}: leads={bucket['total']}, replies={bucket['replied']}, "
            f"positive={bucket['positive']}, demos={bucket['demos']}"
        )
    return rows
