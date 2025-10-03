# Gitea Mirror Manager

[![All Contributors](https://img.shields.io/github/all-contributors/alan-turing-institute/gitea-mirror-manager?color=ee8449&style=flat-square)](#contributors)

Given two running Gitea instances, with this container you can accomplish the following:

1. In the Gitea instance with access to the internet, you can mirror an external repository, like the ones hosted in GitHub.
2. In the Gitea instance with access to the first instance, you can mirror the repository copy created in number 1.

We use this behaviour to provide secure access to external repositories to environments with limited internet connectivity.

## Getting Started

These instructions will cover usage information and for the docker container

### Pre-requisites

In order to run this container you'll need docker installed.

- [Windows](https://docs.docker.com/desktop/setup/install/windows-install/)
- [OS X](https://docs.docker.com/desktop/setup/install/mac-install/)
- [Linux](https://docs.docker.com/desktop/setup/install/linux/)

### Usage

#### Running the container

Install and run from the command line using:

```shell
docker run ghcr.io/alan-turing-institute/gitea-mirror-manager:main
```

#### Environment Variables

- `MIRROR_SERVER_URL` - The URL of the Gitea server **with** access to an external Git repository via the Internet.
- `MIRROR_SERVER_USERNAME` - The username of a user in `MIRROR_SERVER_URL`.
- `MIRROR_SERVER_PASSWORD` - The password of a user in `MIRROR_SERVER_URL` with username `MIRROR_SERVER_USERNAME`.
- `WORKSPACE_SERVER_URL` - The URL of the Gitea server **without** access to an external Git repository.
- `WORKSPACE_SERVER_USERNAME` - The username of a user in `WORKSPACE_SERVER_URL`.
- `WORKSPACE_SERVER_PASSWORD` - The password of a user in `WORKSPACE_SERVER_URL` with username `WORKSPACE_SERVER_URL`.
- `REPOSITORY_DATA` - Information of the external repository to mirror in JSON format. It should contain:

  ```json
  {
    "repositories": [
      {
        "repository_name": "An identifier for the Git repository to mirror.",
        "repository_url": "The URL of the GitHub repository to mirror, like https://github.com/alan-turing-institute/gitea-mirror-manager.",
        "repository_auth_token": "A read-only GitH personal access token, with access to the repository to mirror."
      }
    ]
  }
  ```


#### Useful File Locations

- `gitea_mirror_manager/mirrors.py` - The Python module that setups the mirrors in both Gitea servers, using  [REST API calls](https://docs.gitea.com/api/1.24/).

## Built With

- Python v3.13
- Requests v2.32.5

## Find Us

- [GitHub](https://github.com/alan-turing-institute)
- [The Research Engineering Group at the Alan Turing Institute](https://www.turing.ac.uk/work-turing/research/research-engineering-group)


## Versioning

We use [SemVer](http://semver.org/) for versioning. For the versions available, see the
[tags on this repository](https://github.com/alan-turing-institute/gitea-mirror-manager/tags).

## Contributors

<!-- ALL-CONTRIBUTORS-LIST:START - Do not remove or modify this section -->
<!-- prettier-ignore-start -->
<!-- markdownlint-disable -->

<!-- markdownlint-restore -->
<!-- prettier-ignore-end -->

<!-- ALL-CONTRIBUTORS-LIST:END -->

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.


