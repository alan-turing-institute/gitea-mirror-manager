import importlib
import json
from unittest.mock import MagicMock, call, patch

import pytest
import requests

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
        assert (
            mirrors.MIRROR_INTERVAL_MINUTES == mirrors.DEFAULT_MIRROR_INTERVAL_MINUTES
        )
        assert mirrors.MIRROR_INTERVAL_MINUTES == 10
    finally:
        importlib.reload(mirrors)


def test_mirror_interval_minutes_raises_when_not_a_number(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MIRROR_INTERVAL_MINUTES", "not-a-number")

    try:
        with pytest.raises(ValueError, match="not-a-number"):
            importlib.reload(mirrors)
    finally:
        monkeypatch.delenv("MIRROR_INTERVAL_MINUTES", raising=False)
        importlib.reload(mirrors)


@pytest.mark.parametrize("failed_index", [0, 1, 2])
@pytest.mark.parametrize("failed_stage", ["github", "gitea"])
@pytest.mark.parametrize("failure_kind", ["rejection", "connection"])
def test_main_continues_after_individual_migration_failures(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    failed_index: int,
    failed_stage: str,
    failure_kind: str,
) -> None:
    repositories = [
        {
            "repository_name": f"repo-{i}",
            "repository_url": f"https://github.com/example/repo-{i}",
            "repository_auth_token": f"synthetic-token-{i}",
        }
        for i in range(3)
    ]
    monkeypatch.setattr(mirrors, "REPOSITORY_DATA", {"repositories": repositories})
    secret = "synthetic-secret-from-server"
    attempted = []
    completed = []

    def respond(_url, **kwargs):
        data = json.loads(kwargs["data"])
        name = data["repo_name"]
        stage = data["service"]
        attempted.append((stage, name))
        response = MagicMock()
        bad_name = f"repo-{failed_index}" + ("-mirror" if stage == "gitea" else "")
        if stage == failed_stage and name == bad_name:
            if failure_kind == "connection":
                raise requests.ConnectionError(secret)
            response.status_code = 401
            response.json.return_value = {"message": secret}
        else:
            response.status_code = 201
            response.json.return_value = {"owner": {"username": "owner"}, "name": name}
            completed.append((stage, name))
        return response

    with (
        patch.object(
            mirrors, "obtain_api_token", side_effect=["mirror-api", "workspace-api"]
        ),
        patch.object(mirrors, "get_repositories", return_value=[]),
        patch.object(mirrors.requests, "post", side_effect=respond),
        pytest.raises(RuntimeError, match="1 of 3") as error,
    ):
        mirrors.main()

    for i in range(3):
        assert ("github", f"repo-{i}") in attempted
        if i != failed_index:
            assert ("github", f"repo-{i}") in completed
            assert ("gitea", f"repo-{i}-mirror") in completed
    if failed_stage == "github":
        assert ("gitea", f"repo-{failed_index}-mirror") not in attempted
    assert f"repo-{failed_index}" in caplog.text
    assert secret not in caplog.text
    assert secret not in str(error.value)
    assert error.value.__context__ is None


def test_main_reports_all_failed_repositories(monkeypatch: pytest.MonkeyPatch) -> None:
    repositories = [
        {
            "repository_name": name,
            "repository_url": f"https://github.com/example/{name}",
            "repository_auth_token": "synthetic-token",
        }
        for name in ("one", "two")
    ]
    monkeypatch.setattr(mirrors, "REPOSITORY_DATA", {"repositories": repositories})
    response = MagicMock(status_code=403)
    response.json.return_value = {"message": "denied"}

    with (
        patch.object(
            mirrors, "obtain_api_token", side_effect=["mirror-api", "workspace-api"]
        ),
        patch.object(mirrors, "get_repositories", return_value=[]),
        patch.object(mirrors.requests, "post", return_value=response) as post,
        pytest.raises(RuntimeError, match="2 of 2"),
    ):
        mirrors.main()

    assert post.call_count == 2


@pytest.mark.parametrize(
    "repositories",
    [
        [],
        [
            {
                "repository_name": "repo",
                "repository_url": "https://github.com/example/repo",
                "repository_auth_token": "synthetic-token",
            }
        ],
    ],
)
def test_main_preserves_successful_runs(
    monkeypatch: pytest.MonkeyPatch, repositories
) -> None:
    monkeypatch.setattr(mirrors, "REPOSITORY_DATA", {"repositories": repositories})
    with (
        patch.object(
            mirrors, "obtain_api_token", side_effect=["mirror-api", "workspace-api"]
        ),
        patch.object(
            mirrors, "get_repositories", side_effect=[["old"], ["old-mirror"]]
        ),
        patch.object(mirrors, "delete_repository") as delete,
        patch.object(
            mirrors, "create_migration", return_value=("owner", "repo")
        ) as migrate,
    ):
        assert mirrors.main() is None

    assert migrate.call_count == 2 * len(repositories)
    assert delete.call_count == 2
    if repositories:
        assert migrate.call_args_list == [
            call(
                repository_name="repo",
                repository_url="https://github.com/example/repo",
                repository_auth_token="synthetic-token",
                gitea_url=mirrors.MIRROR_SERVER_URL,
                token="mirror-api",
                service="github",
                mirror_interval_minutes=10,
            ),
            call(
                repository_name="repo-mirror",
                repository_url=f"{mirrors.MIRROR_SERVER_URL}/owner/repo",
                repository_auth_token="mirror-api",
                gitea_url=mirrors.WORKSPACE_SERVER_URL,
                token="workspace-api",
                service="gitea",
                mirror_interval_minutes=10,
            ),
        ]


def test_main_still_fails_fast_on_global_setup_error() -> None:
    with (
        patch.object(
            mirrors, "obtain_api_token", side_effect=RuntimeError("setup failed")
        ),
        patch.object(mirrors, "delete_repository") as delete,
        patch.object(mirrors, "create_migration") as migrate,
        pytest.raises(RuntimeError, match="setup failed"),
    ):
        mirrors.main()

    delete.assert_not_called()
    migrate.assert_not_called()
