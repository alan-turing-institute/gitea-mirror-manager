import importlib
import json
from unittest.mock import MagicMock, patch

import pytest

from gitea_mirror_manager import mirrors


@pytest.mark.parametrize(
    ("minutes", "expected"),
    [
        (10, "0h10m0s"),
        (90, "1h30m0s"),
        (120, "2h0m0s"),
    ],
)
def test_to_gitea_duration(minutes: int, expected: str) -> None:
    assert mirrors.to_gitea_duration(minutes) == expected


@pytest.mark.parametrize("value", [0, -1])
def test_validate_mirror_interval_minutes_rejects_invalid_values(value: int) -> None:
    with pytest.raises(ValueError, match="MIRROR_INTERVAL_MINUTES"):
        mirrors.validate_mirror_interval_minutes(value)


@pytest.mark.parametrize("value", [1, 10])
def test_validate_mirror_interval_minutes_accepts_valid_values(value: int) -> None:
    mirrors.validate_mirror_interval_minutes(value)


def test_create_migration_sends_configured_mirror_interval() -> None:
    mirror_interval_minutes = 30
    response = MagicMock()
    response.status_code = 201
    response.json.return_value = {"owner": {"username": "owner"}, "name": "repo"}

    post_target = "gitea_mirror_manager.mirrors.requests.post"
    with patch(post_target, return_value=response) as post:
        mirrors.create_migration(
            repository_url="https://github.com/example/repo",
            repository_name="repo",
            repository_auth_token="token",
            gitea_url="https://mirror.example.com",
            token="access-token",
            service="github",
            mirror_interval_minutes=mirror_interval_minutes,
        )

    sent_data = json.loads(post.call_args.kwargs["data"])
    assert sent_data["mirror_interval"] == mirrors.to_gitea_duration(
        mirror_interval_minutes
    )


def test_mirror_interval_minutes_defaults_when_env_var_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MIRROR_INTERVAL_MINUTES", raising=False)

    try:
        importlib.reload(mirrors)
        assert mirrors.MIRROR_INTERVAL_MINUTES == mirrors.DEFAULT_MIRROR_INTERVAL_MINUTES
        assert mirrors.MIRROR_INTERVAL_MINUTES == 10
    finally:
        importlib.reload(mirrors)
