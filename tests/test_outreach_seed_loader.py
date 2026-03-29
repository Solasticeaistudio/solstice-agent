import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def _write_json(path: Path, payload):
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_load_seed_bundle_adds_campaign_and_leads(tmp_path):
    from solstice_agent.outreach.seed_loader import load_seed_bundle
    from solstice_agent.outreach.store import OutreachStore

    campaign_path = tmp_path / "campaign.json"
    leads_path = tmp_path / "leads.json"
    store_root = tmp_path / "store"

    _write_json(
        campaign_path,
        {
            "id": "camp-test",
            "name": "Test Campaign",
            "campaign_type": "customer",
            "status": "draft",
            "persona_name": "outreach_war_room",
        },
    )
    _write_json(
        leads_path,
        [
            {
                "email": "one@example.com",
                "first_name": "One",
                "last_name": "Lead",
                "company": "Example One",
                "campaign_id": "camp-test",
            },
            {
                "email": "two@example.com",
                "first_name": "Two",
                "last_name": "Lead",
                "company": "Example Two",
                "campaign_id": "camp-test",
            },
        ],
    )

    result = load_seed_bundle(str(campaign_path), str(leads_path), store_root=str(store_root))
    assert "Leads added: 2" in result

    store = OutreachStore(root=str(store_root))
    campaign = store.get_campaign("camp-test")
    assert campaign is not None
    assert campaign.persona_name == "outreach_war_room"
    assert len(store.list_leads(campaign_id="camp-test")) == 2


def test_load_seed_bundle_skips_existing_without_replace(tmp_path):
    from solstice_agent.outreach.seed_loader import load_seed_bundle
    from solstice_agent.outreach.store import OutreachStore

    campaign_path = tmp_path / "campaign.json"
    leads_path = tmp_path / "leads.json"
    store_root = tmp_path / "store"

    _write_json(
        campaign_path,
        {
            "id": "camp-test",
            "name": "Test Campaign",
            "campaign_type": "customer",
            "status": "draft",
        },
    )
    _write_json(
        leads_path,
        [
            {
                "email": "one@example.com",
                "first_name": "One",
                "last_name": "Lead",
                "company": "Example One",
                "campaign_id": "camp-test",
            }
        ],
    )

    load_seed_bundle(str(campaign_path), str(leads_path), store_root=str(store_root))
    store = OutreachStore(root=str(store_root))
    lead = store.get_lead_by_email("one@example.com")
    assert lead is not None
    original_id = lead.id

    with pytest.raises(ValueError):
        load_seed_bundle(str(campaign_path), str(leads_path), store_root=str(store_root))

    store = OutreachStore(root=str(store_root))
    assert store.get_lead_by_email("one@example.com").id == original_id


def test_load_seed_bundle_replaces_existing_by_email(tmp_path):
    from solstice_agent.outreach.seed_loader import load_seed_bundle
    from solstice_agent.outreach.store import OutreachStore

    campaign_path = tmp_path / "campaign.json"
    leads_path = tmp_path / "leads.json"
    store_root = tmp_path / "store"

    _write_json(
        campaign_path,
        {
            "id": "camp-test",
            "name": "Test Campaign",
            "campaign_type": "customer",
            "status": "draft",
        },
    )
    _write_json(
        leads_path,
        [
            {
                "email": "one@example.com",
                "first_name": "One",
                "last_name": "Lead",
                "company": "Example One",
                "campaign_id": "camp-test",
            }
        ],
    )

    load_seed_bundle(str(campaign_path), str(leads_path), store_root=str(store_root))

    _write_json(
        leads_path,
        [
            {
                "email": "one@example.com",
                "first_name": "Updated",
                "last_name": "Lead",
                "company": "Example One Updated",
                "campaign_id": "camp-test",
            }
        ],
    )

    result = load_seed_bundle(
        str(campaign_path),
        str(leads_path),
        store_root=str(store_root),
        replace=True,
    )
    assert "Leads updated: 1" in result

    store = OutreachStore(root=str(store_root))
    lead = store.get_lead_by_email("one@example.com")
    assert lead is not None
    assert lead.first_name == "Updated"
    assert lead.company == "Example One Updated"


def test_outreach_load_seeds_tool_wrapper(tmp_path):
    from solstice_agent.outreach.tools import outreach_load_seeds
    from solstice_agent.outreach.store import OutreachStore

    campaign_path = tmp_path / "campaign.json"
    leads_path = tmp_path / "leads.json"
    store_root = tmp_path / "store"

    _write_json(
        campaign_path,
        {
            "id": "camp-tool",
            "name": "Tool Campaign",
            "campaign_type": "customer",
            "status": "draft",
        },
    )
    _write_json(
        leads_path,
        [
            {
                "email": "tool@example.com",
                "first_name": "Tool",
                "last_name": "Lead",
                "company": "Example Tool",
                "campaign_id": "camp-tool",
            }
        ],
    )

    result = outreach_load_seeds(
        campaign_seed_path=str(campaign_path),
        leads_seed_path=str(leads_path),
        store_root=str(store_root),
    )
    assert "Loaded campaign 'Tool Campaign' (camp-tool)" in result

    store = OutreachStore(root=str(store_root))
    assert store.get_campaign("camp-tool") is not None
    assert store.get_lead_by_email("tool@example.com") is not None


def test_cli_outreach_load_seeds(tmp_path, monkeypatch, capsys):
    from solstice_agent.cli import main
    from solstice_agent.outreach.store import OutreachStore

    campaign_path = tmp_path / "campaign.json"
    leads_path = tmp_path / "leads.json"
    store_root = tmp_path / "store"

    _write_json(
        campaign_path,
        {
            "id": "camp-cli",
            "name": "CLI Campaign",
            "campaign_type": "customer",
            "status": "draft",
        },
    )
    _write_json(
        leads_path,
        [
            {
                "email": "cli@example.com",
                "first_name": "CLI",
                "last_name": "Lead",
                "company": "Example CLI",
                "campaign_id": "camp-cli",
            }
        ],
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "sol",
            "--outreach-load-seeds",
            str(campaign_path),
            str(leads_path),
            "--outreach-store-root",
            str(store_root),
        ],
    )

    main()
    output = capsys.readouterr().out
    assert "Loaded campaign 'CLI Campaign' (camp-cli)" in output

    store = OutreachStore(root=str(store_root))
    assert store.get_campaign("camp-cli") is not None
    assert store.get_lead_by_email("cli@example.com") is not None


def test_outreach_prepare_draft_batch_creates_compose_artifacts(tmp_path):
    from solstice_agent.outreach.seed_loader import load_seed_bundle
    from solstice_agent.outreach.composer import outreach_prepare_draft_batch
    from solstice_agent.outreach.store import OutreachStore

    campaign_path = tmp_path / "campaign.json"
    leads_path = tmp_path / "leads.json"
    store_root = tmp_path / "store"

    _write_json(
        campaign_path,
        {
            "id": "camp-draft",
            "name": "Draft Campaign",
            "campaign_type": "customer",
            "status": "draft",
            "persona_name": "outreach_war_room",
            "value_proposition": "Paid Decision Sprint",
            "email_templates": {"initial": "Be concise."},
        },
    )
    _write_json(
        leads_path,
        [
            {
                "email": "draft1@example.com",
                "first_name": "Draft",
                "last_name": "One",
                "company": "Example One",
                "campaign_id": "camp-draft",
                "score": 80,
                "stage": "qualified",
            },
            {
                "email": "draft2@example.com",
                "first_name": "Draft",
                "last_name": "Two",
                "company": "Example Two",
                "campaign_id": "camp-draft",
                "score": 81,
                "stage": "qualified",
            },
        ],
    )

    load_seed_bundle(str(campaign_path), str(leads_path), store_root=str(store_root))

    from solstice_agent.outreach import composer as composer_module
    original_get_store = composer_module.get_store
    composer_module.get_store = lambda: OutreachStore(root=str(store_root))
    try:
        result = outreach_prepare_draft_batch("camp-draft", limit=2)
    finally:
        composer_module.get_store = original_get_store

    assert "Prepared 2 compose artifacts for 'Draft Campaign'" in result
    drafts = list((store_root / "drafts").glob("*compose*.json"))
    assert len(drafts) == 2
    payload = json.loads(drafts[0].read_text(encoding="utf-8"))
    assert payload["email_type"] == "initial"
    assert "COMPOSE EMAIL for INITIAL outreach." in payload["context"]


def test_triage_reply_detects_pricing_request(tmp_path):
    from solstice_agent.outreach.seed_loader import load_seed_bundle
    from solstice_agent.outreach.store import OutreachStore
    from solstice_agent.outreach.models import Conversation, EmailMessage, LeadStage
    from solstice_agent.outreach.reply_triage import triage_reply

    campaign_path = tmp_path / "campaign.json"
    leads_path = tmp_path / "leads.json"
    store_root = tmp_path / "store"

    _write_json(campaign_path, {"id": "camp-reply", "name": "Reply Campaign", "campaign_type": "customer", "status": "draft"})
    _write_json(leads_path, [{"email": "reply@example.com", "first_name": "Reply", "last_name": "Lead", "company": "Example", "campaign_id": "camp-reply", "stage": "replied"}])
    load_seed_bundle(str(campaign_path), str(leads_path), store_root=str(store_root))

    store = OutreachStore(root=str(store_root))
    lead = store.get_lead_by_email("reply@example.com")
    lead.stage = LeadStage.REPLIED
    store.save_lead(lead)
    store.save_conversation(
        Conversation(
            lead_id=lead.id,
            campaign_id="camp-reply",
            messages=[EmailMessage(direction="inbound", subject="Re: pricing", body="This looks interesting. What does pricing look like?")],
        )
    )

    from solstice_agent.outreach import reply_triage as triage_module
    original_get_store = triage_module.get_store
    triage_module.get_store = lambda: OutreachStore(root=str(store_root))
    try:
        result = triage_reply(lead.id)
    finally:
        triage_module.get_store = original_get_store

    assert "Intent: pricing_request" in result
    assert "Safe to auto-reply: no" in result


def test_prepare_reply_batch_prepares_safe_and_escalates_sensitive(tmp_path):
    from solstice_agent.outreach.seed_loader import load_seed_bundle
    from solstice_agent.outreach.store import OutreachStore
    from solstice_agent.outreach.models import Conversation, EmailMessage, LeadStage
    from solstice_agent.outreach.reply_triage import outreach_prepare_reply_batch

    campaign_path = tmp_path / "campaign.json"
    leads_path = tmp_path / "leads.json"
    store_root = tmp_path / "store"

    _write_json(
        campaign_path,
        {
            "id": "camp-replies",
            "name": "Reply Campaign",
            "campaign_type": "customer",
            "status": "draft",
            "persona_name": "outreach_war_room",
            "value_proposition": "Paid Decision Sprint",
            "email_templates": {"reply": "Answer directly."},
        },
    )
    _write_json(
        leads_path,
        [
            {"email": "safe@example.com", "first_name": "Safe", "last_name": "Lead", "company": "SafeCo", "campaign_id": "camp-replies", "stage": "replied"},
            {"email": "demo@example.com", "first_name": "Demo", "last_name": "Lead", "company": "DemoCo", "campaign_id": "camp-replies", "stage": "replied"},
        ],
    )
    load_seed_bundle(str(campaign_path), str(leads_path), store_root=str(store_root))

    store = OutreachStore(root=str(store_root))
    safe = store.get_lead_by_email("safe@example.com")
    demo = store.get_lead_by_email("demo@example.com")
    safe.stage = LeadStage.REPLIED
    demo.stage = LeadStage.REPLIED
    store.save_lead(safe)
    store.save_lead(demo)
    store.save_conversation(
        Conversation(
            lead_id=safe.id,
            campaign_id="camp-replies",
            messages=[EmailMessage(direction="inbound", subject="Re: sample", body="Can you send a sample output?")],
        )
    )
    store.save_conversation(
        Conversation(
            lead_id=demo.id,
            campaign_id="camp-replies",
            messages=[EmailMessage(direction="inbound", subject="Re: demo", body="Happy to do a demo next week.")],
        )
    )

    from solstice_agent.outreach import reply_triage as triage_module
    from solstice_agent.outreach import composer as composer_module
    original_triage_get_store = triage_module.get_store
    original_composer_get_store = composer_module.get_store
    triage_module.get_store = lambda: OutreachStore(root=str(store_root))
    composer_module.get_store = lambda: OutreachStore(root=str(store_root))
    try:
        result = outreach_prepare_reply_batch("camp-replies", limit=10, auto_safe_only=True)
    finally:
        triage_module.get_store = original_triage_get_store
        composer_module.get_store = original_composer_get_store

    assert "Prepared reply artifacts: 1" in result
    assert "Escalations: 1" in result
    assert "Intent: interested_needs_more_info" in result
    assert "Intent: demo_request" in result

    drafts = list((store_root / "drafts").glob("*reply-compose*.json"))
    assert len(drafts) == 1


def test_reply_review_queue_labels_pending_replies(tmp_path):
    from solstice_agent.outreach.seed_loader import load_seed_bundle
    from solstice_agent.outreach.store import OutreachStore
    from solstice_agent.outreach.models import Conversation, EmailMessage, LeadStage
    from solstice_agent.outreach.reply_triage import outreach_reply_review_queue

    campaign_path = tmp_path / "campaign.json"
    leads_path = tmp_path / "leads.json"
    store_root = tmp_path / "store"

    _write_json(campaign_path, {"id": "camp-review", "name": "Review Campaign", "campaign_type": "customer", "status": "draft"})
    _write_json(
        leads_path,
        [{"email": "review@example.com", "first_name": "Review", "last_name": "Lead", "company": "ReviewCo", "campaign_id": "camp-review", "stage": "replied"}],
    )
    load_seed_bundle(str(campaign_path), str(leads_path), store_root=str(store_root))

    store = OutreachStore(root=str(store_root))
    lead = store.get_lead_by_email("review@example.com")
    lead.stage = LeadStage.REPLIED
    store.save_lead(lead)
    store.save_conversation(
        Conversation(
            lead_id=lead.id,
            campaign_id="camp-review",
            messages=[EmailMessage(direction="inbound", subject="Re: info", body="Can you send a sample output?")],
        )
    )

    from solstice_agent.outreach import reply_triage as triage_module
    original_get_store = triage_module.get_store
    triage_module.get_store = lambda: OutreachStore(root=str(store_root))
    try:
        result = outreach_reply_review_queue("camp-review", limit=10)
    finally:
        triage_module.get_store = original_get_store

    assert "Intent: interested_needs_more_info" in result
    assert "Safe: yes" in result

    store = OutreachStore(root=str(store_root))
    updated = store.get_lead(lead.id)
    assert "needs_info" in updated.tags
    assert updated.last_detected_intent == "interested_needs_more_info"


def test_outreach_autoreply_safe_sends_only_safe_replies(tmp_path):
    from solstice_agent.outreach.seed_loader import load_seed_bundle
    from solstice_agent.outreach.store import OutreachStore
    from solstice_agent.outreach.models import Conversation, EmailMessage, LeadStage
    from solstice_agent.outreach.autoreply import outreach_autoreply_safe
    from solstice_agent.agent.providers.base import LLMResponse

    class DummyProvider:
        def chat(self, messages, tools=None, temperature=0.7, max_tokens=4096):
            return LLMResponse(text='{"subject":"Sample output","body":"Happy to send a sample output. I can also share a short one-page overview if useful."}')

    campaign_path = tmp_path / "campaign.json"
    leads_path = tmp_path / "leads.json"
    store_root = tmp_path / "store"

    _write_json(
        campaign_path,
        {
            "id": "camp-auto",
            "name": "Auto Campaign",
            "campaign_type": "customer",
            "status": "draft",
            "persona_name": "outreach_war_room",
            "value_proposition": "Paid Decision Sprint",
            "email_templates": {"reply": "Answer directly."},
        },
    )
    _write_json(
        leads_path,
        [
            {"email": "safe@example.com", "first_name": "Safe", "last_name": "Lead", "company": "SafeCo", "campaign_id": "camp-auto", "stage": "replied"},
            {"email": "price@example.com", "first_name": "Price", "last_name": "Lead", "company": "PriceCo", "campaign_id": "camp-auto", "stage": "replied"},
        ],
    )
    load_seed_bundle(str(campaign_path), str(leads_path), store_root=str(store_root))

    store = OutreachStore(root=str(store_root))
    safe = store.get_lead_by_email("safe@example.com")
    price = store.get_lead_by_email("price@example.com")
    safe.stage = LeadStage.REPLIED
    price.stage = LeadStage.REPLIED
    store.save_lead(safe)
    store.save_lead(price)
    store.save_conversation(
        Conversation(
            lead_id=safe.id,
            campaign_id="camp-auto",
            messages=[EmailMessage(direction="inbound", subject="Re: sample", body="Can you send a sample output?")],
        )
    )
    store.save_conversation(
        Conversation(
            lead_id=price.id,
            campaign_id="camp-auto",
            messages=[EmailMessage(direction="inbound", subject="Re: pricing", body="What does pricing look like?")],
        )
    )

    from solstice_agent.outreach import autoreply as autoreply_module
    from solstice_agent.outreach import reply_triage as triage_module
    from solstice_agent.outreach import composer as composer_module
    original_triage_get_store = triage_module.get_store
    original_composer_get_store = composer_module.get_store
    original_send = autoreply_module.outreach_send
    triage_module.get_store = lambda: OutreachStore(root=str(store_root))
    composer_module.get_store = lambda: OutreachStore(root=str(store_root))
    sent = []
    autoreply_module.outreach_send = lambda lead_id, subject, body: sent.append((lead_id, subject, body)) or f"Draft created for {lead_id}"
    try:
        result = outreach_autoreply_safe(DummyProvider(), "camp-auto", limit=10)
    finally:
        triage_module.get_store = original_triage_get_store
        composer_module.get_store = original_composer_get_store
        autoreply_module.outreach_send = original_send

    assert "Safe autoreply processed: 1" in result
    assert "Escalated: 1" in result
    assert len(sent) == 1
    assert sent[0][1] == "Sample output"


def test_outreach_autoreply_safe_handles_demo_with_booking_link(tmp_path):
    from solstice_agent.outreach.seed_loader import load_seed_bundle
    from solstice_agent.outreach.store import OutreachStore
    from solstice_agent.outreach.models import Conversation, EmailMessage, LeadStage
    from solstice_agent.outreach.autoreply import outreach_autoreply_safe
    from solstice_agent.agent.providers.base import LLMResponse

    class DummyProvider:
        def chat(self, messages, tools=None, temperature=0.7, max_tokens=4096):
            return LLMResponse(text='{"subject":"unused","body":"unused"}')

    campaign_path = tmp_path / "campaign.json"
    leads_path = tmp_path / "leads.json"
    store_root = tmp_path / "store"

    _write_json(
        campaign_path,
        {
            "id": "camp-demo",
            "name": "Demo Campaign",
            "campaign_type": "customer",
            "status": "draft",
            "persona_name": "outreach_war_room",
        },
    )
    _write_json(
        leads_path,
        [{"email": "demo@example.com", "first_name": "Demo", "last_name": "Lead", "company": "DemoCo", "campaign_id": "camp-demo", "stage": "replied"}],
    )
    load_seed_bundle(str(campaign_path), str(leads_path), store_root=str(store_root))

    store = OutreachStore(root=str(store_root))
    lead = store.get_lead_by_email("demo@example.com")
    lead.stage = LeadStage.REPLIED
    store.save_lead(lead)
    store.save_conversation(
        Conversation(
            lead_id=lead.id,
            campaign_id="camp-demo",
            messages=[EmailMessage(direction="inbound", subject="Re: demo", body="Happy to do a demo next week.")],
        )
    )

    from solstice_agent.outreach import autoreply as autoreply_module
    from solstice_agent.outreach import reply_triage as triage_module
    from solstice_agent.outreach import composer as composer_module
    original_triage_get_store = triage_module.get_store
    original_composer_get_store = composer_module.get_store
    original_send = autoreply_module.outreach_send
    triage_module.get_store = lambda: OutreachStore(root=str(store_root))
    composer_module.get_store = lambda: OutreachStore(root=str(store_root))
    sent = []
    autoreply_module.outreach_send = lambda lead_id, subject, body: sent.append((lead_id, subject, body)) or f"Draft created for {lead_id}"
    try:
        result = outreach_autoreply_safe(
            DummyProvider(),
            "camp-demo",
            limit=10,
            booking_link="https://book.example.com/demo",
        )
    finally:
        triage_module.get_store = original_triage_get_store
        composer_module.get_store = original_composer_get_store
        autoreply_module.outreach_send = original_send

    assert "Safe autoreply processed: 1" in result
    assert "Escalated: 0" in result
    assert len(sent) == 1
    assert "https://book.example.com/demo" in sent[0][2]


def test_pipeline_memory_snapshot_shows_deferred_lead(tmp_path):
    from solstice_agent.outreach.seed_loader import load_seed_bundle
    from solstice_agent.outreach.store import OutreachStore
    from solstice_agent.outreach.models import Conversation, EmailMessage, LeadStage
    from solstice_agent.outreach.reply_triage import triage_reply, outreach_pipeline_snapshot

    campaign_path = tmp_path / "campaign.json"
    leads_path = tmp_path / "leads.json"
    store_root = tmp_path / "store"

    _write_json(campaign_path, {"id": "camp-memory", "name": "Memory Campaign", "campaign_type": "customer", "status": "draft"})
    _write_json(
        leads_path,
        [{"email": "later@example.com", "first_name": "Later", "last_name": "Lead", "company": "LaterCo", "campaign_id": "camp-memory", "stage": "replied"}],
    )
    load_seed_bundle(str(campaign_path), str(leads_path), store_root=str(store_root))

    store = OutreachStore(root=str(store_root))
    lead = store.get_lead_by_email("later@example.com")
    lead.stage = LeadStage.REPLIED
    store.save_lead(lead)
    store.save_conversation(
        Conversation(
            lead_id=lead.id,
            campaign_id="camp-memory",
            messages=[EmailMessage(direction="inbound", subject="Re: later", body="Not now. Circle back next quarter.")],
        )
    )

    from solstice_agent.outreach import reply_triage as triage_module
    original_get_store = triage_module.get_store
    triage_module.get_store = lambda: OutreachStore(root=str(store_root))
    try:
        triage_reply(lead.id)
        result = outreach_pipeline_snapshot("camp-memory")
    finally:
        triage_module.get_store = original_get_store

    assert "Intent: not_now" in result
    assert "deferred" in result.lower()


def test_follow_up_compose_uses_pipeline_memory_angle(tmp_path):
    from solstice_agent.outreach.seed_loader import load_seed_bundle
    from solstice_agent.outreach.store import OutreachStore
    from solstice_agent.outreach.models import LeadStage
    from solstice_agent.outreach.composer import outreach_compose

    campaign_path = tmp_path / "campaign.json"
    leads_path = tmp_path / "leads.json"
    store_root = tmp_path / "store"

    _write_json(
        campaign_path,
        {
            "id": "camp-follow",
            "name": "Follow Campaign",
            "campaign_type": "customer",
            "status": "draft",
            "value_proposition": "Paid Decision Sprint",
            "email_templates": {"follow_up": "Keep it useful."},
        },
    )
    _write_json(
        leads_path,
        [
            {
                "email": "follow@example.com",
                "first_name": "Follow",
                "last_name": "Lead",
                "company": "FollowCo",
                "campaign_id": "camp-follow",
                "stage": "contacted",
                "tags": ["needs_info"],
                "last_detected_intent": "interested_needs_more_info",
            }
        ],
    )
    load_seed_bundle(str(campaign_path), str(leads_path), store_root=str(store_root))

    lead = OutreachStore(root=str(store_root)).get_lead_by_email("follow@example.com")
    from solstice_agent.outreach import composer as composer_module
    original_get_store = composer_module.get_store
    composer_module.get_store = lambda: OutreachStore(root=str(store_root))
    try:
        context = outreach_compose(lead.id, email_type="follow_up")
    finally:
        composer_module.get_store = original_get_store

    assert "This lead asked for more information." in context
    assert "Last detected intent: interested_needs_more_info" in context


def test_outreach_analytics_and_next_actions(tmp_path):
    from solstice_agent.outreach.seed_loader import load_seed_bundle
    from solstice_agent.outreach.store import OutreachStore
    from solstice_agent.outreach.analytics import outreach_analytics, outreach_next_best_actions

    campaign_path = tmp_path / "campaign.json"
    leads_path = tmp_path / "leads.json"
    store_root = tmp_path / "store"

    _write_json(campaign_path, {"id": "camp-analytics", "name": "Analytics Campaign", "campaign_type": "customer", "status": "draft"})
    _write_json(
        leads_path,
        [
            {
                "email": "demo@example.com",
                "first_name": "Demo",
                "last_name": "Lead",
                "company": "DemoCo",
                "industry": "Private Equity",
                "campaign_id": "camp-analytics",
                "stage": "engaged",
                "emails_sent": 1,
                "emails_received": 1,
                "tags": ["demo_requested", "engaged_positive"],
                "last_detected_intent": "demo_request",
            },
            {
                "email": "cold@example.com",
                "first_name": "Cold",
                "last_name": "Lead",
                "company": "ColdCo",
                "industry": "Reinsurance",
                "campaign_id": "camp-analytics",
                "stage": "qualified",
                "score": 88,
            },
        ],
    )
    load_seed_bundle(str(campaign_path), str(leads_path), store_root=str(store_root))

    from solstice_agent.outreach import analytics as analytics_module
    original_get_store = analytics_module.get_store
    analytics_module.get_store = lambda: OutreachStore(root=str(store_root))
    try:
        report = outreach_analytics("camp-analytics")
        ranked = outreach_next_best_actions("camp-analytics", limit=5)
    finally:
        analytics_module.get_store = original_get_store

    assert "Demo requests: 1" in report
    assert "Private Equity: leads=1, replies=1, positive=1, demos=1" in report
    assert "demo_interest" in ranked
    assert "ready_for_initial_outreach" in ranked


def test_outreach_exports_create_artifacts(tmp_path):
    from solstice_agent.outreach.seed_loader import load_seed_bundle
    from solstice_agent.outreach.store import OutreachStore
    from solstice_agent.outreach.sync_queue import outreach_export_crm, outreach_export_meeting_queue

    campaign_path = tmp_path / "campaign.json"
    leads_path = tmp_path / "leads.json"
    store_root = tmp_path / "store"

    _write_json(campaign_path, {"id": "camp-export", "name": "Export Campaign", "campaign_type": "customer", "status": "draft"})
    _write_json(
        leads_path,
        [
            {
                "email": "export@example.com",
                "first_name": "Export",
                "last_name": "Lead",
                "company": "ExportCo",
                "campaign_id": "camp-export",
                "stage": "engaged",
                "tags": ["demo_requested"],
                "last_detected_intent": "demo_request",
            }
        ],
    )
    load_seed_bundle(str(campaign_path), str(leads_path), store_root=str(store_root))

    from solstice_agent.outreach import sync_queue as sync_module
    original_get_store = sync_module.get_store
    sync_module.get_store = lambda: OutreachStore(root=str(store_root))
    try:
        crm_result = outreach_export_crm("camp-export")
        meeting_result = outreach_export_meeting_queue("camp-export")
    finally:
        sync_module.get_store = original_get_store

    assert "CRM export created:" in crm_result
    assert "Meeting queue export created:" in meeting_result
    exports = list((store_root / "exports").glob("*.json"))
    assert len(exports) >= 2


def test_outreach_push_webhooks(tmp_path, monkeypatch):
    from solstice_agent.outreach.seed_loader import load_seed_bundle
    from solstice_agent.outreach.store import OutreachStore
    from solstice_agent.outreach.sync_queue import outreach_push_crm, outreach_push_meeting_queue

    campaign_path = tmp_path / "campaign.json"
    leads_path = tmp_path / "leads.json"
    store_root = tmp_path / "store"

    _write_json(campaign_path, {"id": "camp-push", "name": "Push Campaign", "campaign_type": "customer", "status": "draft"})
    _write_json(
        leads_path,
        [
            {
                "email": "push@example.com",
                "first_name": "Push",
                "last_name": "Lead",
                "company": "PushCo",
                "campaign_id": "camp-push",
                "stage": "engaged",
                "tags": ["demo_requested"],
            }
        ],
    )
    load_seed_bundle(str(campaign_path), str(leads_path), store_root=str(store_root))

    calls = []

    class DummyResponse:
        def raise_for_status(self):
            return None

    class DummyClient:
        def __init__(self, timeout=20.0):
            self.timeout = timeout
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False
        def post(self, url, json):
            calls.append((url, json))
            return DummyResponse()

    from solstice_agent.outreach import sync_queue as sync_module
    original_get_store = sync_module.get_store
    original_client = sync_module.httpx.Client
    sync_module.get_store = lambda: OutreachStore(root=str(store_root))
    sync_module.httpx.Client = DummyClient
    try:
        crm_result = outreach_push_crm("camp-push", "https://example.com/crm")
        meeting_result = outreach_push_meeting_queue("camp-push", "https://example.com/meetings")
    finally:
        sync_module.get_store = original_get_store
        sync_module.httpx.Client = original_client

    assert "CRM webhook push complete." in crm_result
    assert "Meeting webhook push complete." in meeting_result
    assert len(calls) == 2
