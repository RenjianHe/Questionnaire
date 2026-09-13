from handlers.transunion_mock import handler


def test_same_user_id_is_stable():
    first = handler({"userId": "u-001"}, None)
    second = handler({"userId": "u-001"}, None)
    assert first == second


def test_returns_only_700_or_500():
    for user_id in ["u-001", "u-002", "abc", "xyz123", ""]:
        result = handler({"userId": user_id}, None)
        assert result["creditScore"] in (700, 500)
