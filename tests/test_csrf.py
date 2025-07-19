from pyview.csrf import generate_csrf_token, validate_csrf_token


def test_can_validate_tokens():
    t = generate_csrf_token("test")
    assert validate_csrf_token(t, "test")


def test_can_validate_tokens_with_salt():
    t = generate_csrf_token("test", salt="test-salt")
    assert validate_csrf_token(t, "test", salt="test-salt")


def test_can_validate_tokens_with_different_salt():
    t = generate_csrf_token("test", salt="test-salt")
    assert not validate_csrf_token(t, "test", salt="test-salt-2")


def test_can_validate_tokens_with_different_value():
    t = generate_csrf_token("test", salt="test-salt")
    assert not validate_csrf_token(t, "test-2", salt="test-salt")
