import base64
import json
from urllib.parse import quote

from app.token_tool import decode_jwt, explain_token, token_from_login_session


def encode_part(payload: dict) -> str:
    raw = json.dumps(payload).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def test_token_tool_extracts_subscription_token_from_login_session():
    token = "a.b.c"
    value = quote(json.dumps({"data": {"subscriptionToken": token}}))

    assert token_from_login_session(value) == token


def test_token_tool_decodes_and_explains_jwt_without_signature_check():
    token = ".".join(
        [
            encode_part({"alg": "RS256", "kid": "1"}),
            encode_part(
                {
                    "iss": "F1TV",
                    "SubscriptionStatus": "active",
                    "SubscribedProduct": "F1 TV Access Monthly",
                    "Subscription": "ACCESS",
                    "SubscriberId": "123",
                    "exp": 4102444800,
                    "iat": 1700000000,
                }
            ),
            "signature",
        ]
    )

    decoded = decode_jwt(token)
    explained = explain_token("test", token)

    assert decoded["header"]["alg"] == "RS256"
    assert explained["subscription_status"] == "active"
    assert explained["usable_for_signalr"] is True
