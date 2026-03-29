from solstice_agent.outreach import composer as composer_module
from solstice_agent.outreach.models import Campaign, CampaignStatus, CampaignType, Lead, LeadStage, LeadType
from solstice_agent.outreach.store import OutreachStore


class _FakeEmailChannel:
    last_call = None

    def __init__(self, config):
        self.config = config

    def is_configured(self):
        return True

    def send_message(self, recipient_id, text, metadata=None):
        _FakeEmailChannel.last_call = {
            "recipient_id": recipient_id,
            "text": text,
            "metadata": metadata or {},
            "config": self.config,
        }
        return {"success": True, "mode": metadata.get("mode", "send")}


def test_outreach_send_appends_signature_and_uses_html_for_graph(tmp_path, monkeypatch):
    store_root = tmp_path / "store"
    store = OutreachStore(root=str(store_root))

    campaign = Campaign(
        id="camp-test",
        name="Test Campaign",
        campaign_type=CampaignType.CUSTOMER,
        status=CampaignStatus.ACTIVE,
        draft_only=False,
        mailbox="outreach@example.com",
    )
    lead = Lead(
        id="lead-one",
        lead_type=LeadType.CUSTOMER,
        stage=LeadStage.QUALIFIED,
        email="contact@example.com",
        first_name="Alex",
        last_name="Test",
        company="Example Corp",
        campaign_id=campaign.id,
    )
    store.save_campaign(campaign)
    store.save_lead(lead)

    monkeypatch.setattr(composer_module, "get_store", lambda: OutreachStore(root=str(store_root)))
    monkeypatch.setenv("GATEWAY_EMAIL_PROVIDER", "graph")
    monkeypatch.setenv("GATEWAY_EMAIL_ADDRESS", "agent@example.com")
    monkeypatch.setenv("GATEWAY_EMAIL_GRAPH_USER", "outreach@example.com")
    monkeypatch.setattr(
        "solstice_agent.gateway.channels.email_channel.EmailChannel",
        _FakeEmailChannel,
    )

    result = composer_module.outreach_send("lead-one", "Test subject", "Short body.")

    assert "Email sent to Alex Test" in result
    assert _FakeEmailChannel.last_call is not None
    assert _FakeEmailChannel.last_call["metadata"]["content_type"] == "HTML"
    assert "solsticestudio.ai" in _FakeEmailChannel.last_call["text"]
    conversation = OutreachStore(root=str(store_root)).get_conversation("lead-one")
    assert conversation is not None
