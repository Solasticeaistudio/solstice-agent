"""
Prospector
==========
Lead discovery via web search + browser scraping.

Flow: prospect_search → prospect_research → prospect_qualify → prospect_add
"""

import logging
from .store import get_store
from .models import Lead, LeadType, LeadStage

log = logging.getLogger("solstice.outreach.prospector")


def prospect_search(query: str, campaign_id: str, max_results: int = 10) -> str:
    """Search the web for potential leads matching campaign criteria."""
    store = get_store()
    campaign = store.get_campaign(campaign_id)
    if not campaign:
        return f"Error: Campaign '{campaign_id}' not found."

    from ..tools.web import web_search
    results = web_search(query, max_results=max_results)

    return (
        f"Prospecting for '{campaign.name}' ({campaign.campaign_type.value}):\n"
        f"Query: {query}\n\n"
        f"{results}\n\n"
        f"Next: Use prospect_research on promising URLs, then prospect_qualify, then prospect_add."
    )


def prospect_research(url: str, campaign_id: str) -> str:
    """Deep research a company/person by visiting their website."""
    store = get_store()
    campaign = store.get_campaign(campaign_id)
    if not campaign:
        return f"Error: Campaign '{campaign_id}' not found."

    from ..tools.browser import browser_navigate, browser_read

    nav_result = browser_navigate(url)
    content = browser_read(max_length=8000)

    return (
        f"Research for '{campaign.name}':\n"
        f"URL: {url}\n"
        f"Navigation: {nav_result}\n\n"
        f"Page content:\n{content}\n\n"
        f"Extract: company name, key people + titles, email addresses, "
        f"company description, industry, pain points Solstice could solve. "
        f"Then use prospect_qualify to score this lead."
    )


def prospect_qualify(
    campaign_id: str,
    company: str,
    contact_name: str,
    email: str,
    title: str = "",
    industry: str = "",
    company_description: str = "",
    pain_points: str = "",
    research_notes: str = "",
    source_url: str = "",
) -> str:
    """Qualify and score a potential lead. Returns scoring context for Sol."""
    store = get_store()
    campaign = store.get_campaign(campaign_id)
    if not campaign:
        return f"Error: Campaign '{campaign_id}' not found."

    existing = store.get_lead_by_email(email)
    if existing:
        return (
            f"Lead already exists: {existing.first_name} {existing.last_name} "
            f"at {existing.company} (ID: {existing.id}, stage: {existing.stage.value})"
        )

    pain_list = [p.strip() for p in pain_points.split(",") if p.strip()] if pain_points else []

    return (
        f"Lead qualification for '{campaign.name}' ({campaign.campaign_type.value}):\n\n"
        f"Target criteria: {campaign.target_criteria}\n"
        f"Target industries: {', '.join(campaign.target_industries) or 'any'}\n"
        f"Target titles: {', '.join(campaign.target_titles) or 'any'}\n\n"
        f"Candidate:\n"
        f"  Name: {contact_name}\n"
        f"  Title: {title}\n"
        f"  Company: {company}\n"
        f"  Industry: {industry}\n"
        f"  Description: {company_description}\n"
        f"  Pain points: {', '.join(pain_list) or 'unknown'}\n"
        f"  Research: {research_notes}\n\n"
        f"Score this lead 0-100. If score >= 60, use prospect_add to add them. "
        f"Consider: industry fit, title/seniority, pain point alignment with Solstice, company size."
    )


def prospect_add(
    campaign_id: str,
    email: str,
    first_name: str,
    last_name: str,
    company: str,
    title: str = "",
    industry: str = "",
    company_url: str = "",
    company_description: str = "",
    pain_points: str = "",
    research_notes: str = "",
    score: int = 50,
    score_reasons: str = "",
    source_url: str = "",
) -> str:
    """Add a qualified lead to a campaign."""
    store = get_store()
    campaign = store.get_campaign(campaign_id)
    if not campaign:
        return f"Error: Campaign '{campaign_id}' not found."

    existing = store.get_lead_by_email(email)
    if existing:
        return f"Lead already exists: {existing.id} ({existing.email})"

    pain_list = [p.strip() for p in pain_points.split(",") if p.strip()] if pain_points else []
    reason_list = [r.strip() for r in score_reasons.split(",") if r.strip()] if score_reasons else []

    lead = Lead(
        lead_type=LeadType(campaign.campaign_type.value),
        stage=LeadStage.QUALIFIED if score >= 60 else LeadStage.DISCOVERED,
        email=email,
        first_name=first_name,
        last_name=last_name,
        title=title,
        company=company,
        company_url=company_url,
        company_description=company_description,
        industry=industry,
        score=score,
        score_reasons=reason_list,
        research_notes=research_notes,
        pain_points=pain_list,
        campaign_id=campaign_id,
        source="prospecting",
        source_url=source_url,
    )

    store.save_lead(lead)

    campaign.leads_discovered += 1
    if lead.stage == LeadStage.QUALIFIED:
        campaign.leads_qualified += 1
    store.save_campaign(campaign)

    return (
        f"Lead added: {lead.first_name} {lead.last_name} ({lead.email})\n"
        f"  Company: {lead.company}\n"
        f"  Score: {lead.score}/100\n"
        f"  Stage: {lead.stage.value}\n"
        f"  ID: {lead.id}"
    )
