import pytest
from services.proactive_service import ProactiveService
from models.schemas import CheckinRespondRequest, CheckinSettings


@pytest.mark.asyncio
async def test_proactive_nudge_generation():
    service = ProactiveService()
    nudge = await service.generate_active_nudge(user_id="test_user")

    assert nudge is not None
    assert nudge.id.startswith("nudge_test_user_")
    assert nudge.category in ["hydration", "nutrition", "fitness", "mental"]
    assert len(nudge.quick_options) > 0


@pytest.mark.asyncio
async def test_proactive_respond():
    service = ProactiveService()
    
    # Test water response
    req = CheckinRespondRequest(
        nudge_id="nudge_1",
        user_id="test_user",
        selected_option_id="opt_w_afternoon_reached",
    )
    result = await service.process_response(req)
    assert "2000" in result.ai_reply or "2L" in result.ai_reply or "rải đều" in result.ai_reply

    # Test veggies response
    req_veggies = CheckinRespondRequest(
        nudge_id="nudge_2",
        user_id="test_user",
        selected_option_id="opt_nut_veggies_yes",
    )
    res_veggies = await service.process_response(req_veggies)
    assert res_veggies.status == "success"
    assert "rau xanh" in res_veggies.ai_reply.lower()


def test_proactive_settings():
    service = ProactiveService()
    settings = service.get_user_settings("test_user")
    assert settings.enable_proactive is True

    new_settings = CheckinSettings(enable_proactive=False, water_checkin=False)
    updated = service.update_user_settings("test_user", new_settings)
    assert updated.enable_proactive is False
