import pytest

from deploy import release


def test_bump_version_files_updates_both_files(tmp_path):
    version_py = tmp_path / "version.py"
    version_py.write_text('__version__ = "0.1.0"\n', encoding="utf-8")
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "x"\nversion = "0.1.0"\ndescription = "y"\n', encoding="utf-8")

    release.bump_version_files("0.2.0", version_py=version_py, pyproject_toml=pyproject)

    assert release.read_current_version(version_py) == "0.2.0"
    assert 'version = "0.2.0"' in pyproject.read_text(encoding="utf-8")


def test_validate_new_version_accepts_greater_version():
    release.validate_new_version("0.2.0", "0.1.0")  # darf nicht abbrechen


def test_validate_new_version_rejects_same_or_lower_version():
    with pytest.raises(SystemExit):
        release.validate_new_version("0.1.0", "0.1.0")
    with pytest.raises(SystemExit):
        release.validate_new_version("0.0.9", "0.1.0")


def test_validate_new_version_rejects_invalid_semver():
    with pytest.raises(SystemExit):
        release.validate_new_version("not-a-version", "0.1.0")


def test_parse_digest_extracts_sha256():
    output = "ghcr.io/weidlingersoft/ws-verlag@sha256:abc123\n"
    assert release._parse_digest(output) == "sha256:abc123"


def test_parse_digest_returns_none_without_digest():
    assert release._parse_digest("<no value>") is None
