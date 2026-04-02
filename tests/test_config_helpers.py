"""Tests for config.py env helpers."""

import pytest

# Import the raw functions before any module caches values.
from config import env_bool, env_int, env_float


class TestEnvBool:
    def test_default_true_when_unset(self, monkeypatch):
        monkeypatch.delenv("TEST_BOOL_VAR", raising=False)
        assert env_bool("TEST_BOOL_VAR", True) is True

    def test_default_false_when_unset(self, monkeypatch):
        monkeypatch.delenv("TEST_BOOL_VAR", raising=False)
        assert env_bool("TEST_BOOL_VAR", False) is False

    def test_empty_string_uses_default(self, monkeypatch):
        monkeypatch.setenv("TEST_BOOL_VAR", "")
        assert env_bool("TEST_BOOL_VAR", True) is True

    def test_whitespace_only_uses_default(self, monkeypatch):
        monkeypatch.setenv("TEST_BOOL_VAR", "   ")
        assert env_bool("TEST_BOOL_VAR", True) is True

    @pytest.mark.parametrize("val", ["1", "true", "True", "TRUE", "yes", "YES", "on", "ON"])
    def test_truthy_values(self, monkeypatch, val):
        monkeypatch.setenv("TEST_BOOL_VAR", val)
        assert env_bool("TEST_BOOL_VAR", False) is True

    @pytest.mark.parametrize("val", ["0", "false", "no", "off", "nope", "2"])
    def test_falsy_values(self, monkeypatch, val):
        monkeypatch.setenv("TEST_BOOL_VAR", val)
        assert env_bool("TEST_BOOL_VAR", True) is False


class TestEnvInt:
    def test_default_when_unset(self, monkeypatch):
        monkeypatch.delenv("TEST_INT_VAR", raising=False)
        assert env_int("TEST_INT_VAR", 42) == 42

    def test_valid_int(self, monkeypatch):
        monkeypatch.setenv("TEST_INT_VAR", "100")
        assert env_int("TEST_INT_VAR", 0) == 100

    def test_invalid_falls_back(self, monkeypatch):
        monkeypatch.setenv("TEST_INT_VAR", "not_a_number")
        assert env_int("TEST_INT_VAR", 7) == 7


class TestEnvFloat:
    def test_default_when_unset(self, monkeypatch):
        monkeypatch.delenv("TEST_FLOAT_VAR", raising=False)
        assert env_float("TEST_FLOAT_VAR", 3.14) == 3.14

    def test_valid_float(self, monkeypatch):
        monkeypatch.setenv("TEST_FLOAT_VAR", "2.718")
        assert env_float("TEST_FLOAT_VAR", 0.0) == pytest.approx(2.718)

    def test_invalid_falls_back(self, monkeypatch):
        monkeypatch.setenv("TEST_FLOAT_VAR", "abc")
        assert env_float("TEST_FLOAT_VAR", 1.0) == 1.0
