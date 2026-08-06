from modules.chat.router import router


def test_chat_v2_route_path_registered():
    paths = {route.path for route in router.routes}
    assert "/chat/stream" in paths