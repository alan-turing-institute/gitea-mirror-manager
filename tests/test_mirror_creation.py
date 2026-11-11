import json
import logging
from unittest.mock import MagicMock, patch

import pytest
import requests

from gitea_mirror_manager import mirrors

MIRROR_API_TOKEN = "mirror-api-token"
WORKSPACE_API_TOKEN = "workspace-api-token"
FAILING_REPOSITORY = "repository-a"
HEALTHY_REPOSITORY = "repository-b"


def build_repository_data(
    repository_names: list[str],
) -> dict[str, list[dict[str, str]]]:
    return {
        "repositories": [
            {
                "repository_name": repository_name,
                "repository_url": f"https://github.com/example/{repository_name}",
                "repository_auth_token": f"{repository_name}-secret-token",
            }
            for repository_name in repository_names
        ]
    }


def build_migration_response(*, status_code: int, repository_name: str) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.text = '{"message": "migration failed"}'
    response.json.return_value = {
        "owner": {"username": "owner"},
        "name": repository_name,
    }
    return response


def prepare_main(
    *, monkeypatch: pytest.MonkeyPatch, repository_names: list[str]
) -> None:
    monkeypatch.setattr(
        mirrors, "REPOSITORY_DATA", build_repository_data(repository_names)
    )
    monkeypatch.setattr(
        mirrors,
        "obtain_api_token",
        lambda **kwargs: (
            MIRROR_API_TOKEN
            if kwargs["gitea_url"] == mirrors.MIRROR_SERVER_URL
            else WORKSPACE_API_TOKEN
        ),
    )
    monkeypatch.setattr(mirrors, "get_repositories", lambda **_: [])


def get_migrated_repository_names(post: MagicMock) -> list[str]:
    return [
        json.loads(call.kwargs["data"])["repo_name"] for call in post.call_args_list
    ]


def post_successful_migration(_url: str, **kwargs: str | dict[str, str]) -> MagicMock:
    repository_name: str = json.loads(str(kwargs["data"]))["repo_name"]
    return build_migration_response(status_code=201, repository_name=repository_name)


@pytest.mark.parametrize(
    "failing_migration_name",
    [FAILING_REPOSITORY, f"{FAILING_REPOSITORY}-mirror"],
    ids=["external-stage", "workspace-stage"],
)
@pytest.mark.parametrize("error_kind", ["gitea-api-error", "connection-error"])
def test_main_continues_after_repository_failure(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    failing_migration_name: str,
    error_kind: str,
) -> None:
    caplog.set_level(logging.INFO, logger="mirror_manager")
    prepare_main(
        monkeypatch=monkeypatch,
        repository_names=[FAILING_REPOSITORY, HEALTHY_REPOSITORY],
    )

    def post_migration(url: str, **kwargs: str | dict[str, str]) -> MagicMock:
        repository_name: str = json.loads(str(kwargs["data"]))["repo_name"]
        if repository_name == failing_migration_name:
            if error_kind == "connection-error":
                error_message = f"Connection to {url} refused"
                raise requests.ConnectionError(error_message)
            return build_migration_response(
                status_code=401, repository_name=repository_name
            )
        return post_successful_migration(url, **kwargs)

    post_target = "gitea_mirror_manager.mirrors.requests.post"
    with (
        patch(post_target, side_effect=post_migration) as post,
        pytest.raises(SystemExit) as exit_info,
    ):
        mirrors.main()

    assert exit_info.value.code == 1
    migrated_repository_names = get_migrated_repository_names(post)
    assert HEALTHY_REPOSITORY in migrated_repository_names
    assert f"{HEALTHY_REPOSITORY}-mirror" in migrated_repository_names

    failure_records = [
        record
        for record in caplog.records
        if record.levelname == "ERROR" and record.exc_info is not None
    ]
    assert len(failure_records) == 1
    assert FAILING_REPOSITORY in failure_records[0].getMessage()

    for secret in [
        MIRROR_API_TOKEN,
        WORKSPACE_API_TOKEN,
        f"{FAILING_REPOSITORY}-secret-token",
        f"{HEALTHY_REPOSITORY}-secret-token",
    ]:
        assert secret not in caplog.text


@pytest.mark.parametrize(
    ("missing_field", "kept_field", "placeholder"),
    [
        ("repository_name", "repository_url", "<missing name>"),
        ("repository_url", "repository_name", "<missing URL>"),
    ],
    ids=["missing-name", "missing-url"],
)
def test_main_continues_after_repository_with_missing_field(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    missing_field: str,
    kept_field: str,
    placeholder: str,
) -> None:
    caplog.set_level(logging.INFO, logger="mirror_manager")
    prepare_main(monkeypatch=monkeypatch, repository_names=[HEALTHY_REPOSITORY])
    broken_repository = build_repository_data([FAILING_REPOSITORY])["repositories"][0]
    del broken_repository[missing_field]
    repository_data = build_repository_data([HEALTHY_REPOSITORY])
    repository_data["repositories"].insert(0, broken_repository)
    monkeypatch.setattr(mirrors, "REPOSITORY_DATA", repository_data)

    post_target = "gitea_mirror_manager.mirrors.requests.post"
    with (
        patch(post_target, side_effect=post_successful_migration) as post,
        pytest.raises(SystemExit) as exit_info,
    ):
        mirrors.main()

    assert exit_info.value.code == 1
    # The broken entry fails before any Gitea call is made.
    assert get_migrated_repository_names(post) == [
        HEALTHY_REPOSITORY,
        f"{HEALTHY_REPOSITORY}-mirror",
    ]

    failure_records = [
        record
        for record in caplog.records
        if record.levelname == "ERROR" and record.exc_info is not None
    ]
    assert len(failure_records) == 1
    assert failure_records[0].exc_info is not None
    assert failure_records[0].exc_info[0] is KeyError
    assert placeholder in failure_records[0].getMessage()
    assert broken_repository[kept_field] in failure_records[0].getMessage()
    assert "Mirrored 1 of 2 repositories." in caplog.text
    assert broken_repository["repository_auth_token"] not in caplog.text


def test_main_succeeds_when_all_repositories_mirror(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="mirror_manager")
    prepare_main(
        monkeypatch=monkeypatch,
        repository_names=[FAILING_REPOSITORY, HEALTHY_REPOSITORY],
    )

    post_target = "gitea_mirror_manager.mirrors.requests.post"
    with patch(post_target, side_effect=post_successful_migration) as post:
        mirrors.main()

    assert len(post.call_args_list) == 4
    assert "Mirrored 2 of 2 repositories." in caplog.text


def test_create_migration_error_includes_non_json_body() -> None:
    response = MagicMock()
    response.status_code = 502
    response.text = "<html>Bad Gateway</html>"
    response.json.side_effect = json.JSONDecodeError("Expecting value", "", 0)

    post_target = "gitea_mirror_manager.mirrors.requests.post"
    with (
        patch(post_target, return_value=response),
        pytest.raises(mirrors.GiteaApiError, match="502") as error_info,
    ):
        mirrors.create_migration(
            repository_url="https://github.com/example/repo",
            repository_name="repo",
            repository_auth_token="token",
            gitea_url="https://mirror.example.com",
            token="access-token",
            service="github",
            mirror_interval_minutes=10,
        )

    assert "<html>Bad Gateway</html>" in str(error_info.value)
