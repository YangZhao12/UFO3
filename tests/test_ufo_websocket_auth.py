from urllib.parse import parse_qs, urlsplit

from ufo.client.websocket import UFOWebSocketClient


def test_with_api_key_adds_encoded_token():
    connection_url = UFOWebSocketClient._with_api_key(
        "ws://localhost:5000/ws", "key with/+symbols"
    )

    assert parse_qs(urlsplit(connection_url).query) == {
        "token": ["key with/+symbols"]
    }


def test_with_api_key_preserves_query_and_replaces_token():
    connection_url = UFOWebSocketClient._with_api_key(
        "ws://localhost:5000/ws?mode=local&token=old", "new"
    )

    assert parse_qs(urlsplit(connection_url).query) == {
        "mode": ["local"],
        "token": ["new"],
    }


def test_with_api_key_leaves_url_unchanged_without_key():
    ws_url = "ws://localhost:5000/ws?mode=local"

    assert UFOWebSocketClient._with_api_key(ws_url, None) == ws_url