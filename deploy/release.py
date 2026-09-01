"""Ein-Kommando-Release: Version hochzaehlen, committen/taggen, Docker-Image bauen und
zu ghcr.io pushen, Digest ermitteln, version.json schreiben und per FTPS auf die Website
hochladen.

Verwendung:
  poetry run python deploy/release.py 0.2.0 --changelog "- Neue Funktion X\n- Fehlerbehebung Y"

Ohne --changelog wird der Text interaktiv abgefragt.

Voraussetzungen:
- Sauberer Git-Arbeitsbaum (keine unversionierten Aenderungen).
- Einmalig `docker login ghcr.io` mit einem GitHub Personal Access Token
  (Scope write:packages, read:packages) - siehe README-DEPLOYMENT.md.
- deploy/.env.deploy mit den FTP-Zugangsdaten (siehe deploy/.env.deploy.example).

Bricht bei jedem Fehler sofort ab, ohne nachfolgende Schritte auszufuehren. Ein
Git-Commit/Tag aus Schritt 3 wird bei einem spaeteren Fehlschlag NICHT automatisch
rueckgaengig gemacht (bewusst einfach gehalten - im Fehlerfall von Hand pruefen/korrigieren).
Ein `git push` erfolgt nie automatisch; der Befehl dafuer wird am Ende nur ausgegeben.
"""
import argparse
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

from packaging.version import InvalidVersion, Version

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deploy_release import ENV_FILE, UPLOAD_DIR, load_env, upload_directory  # noqa: E402

import ftplib

REPO_ROOT = Path(__file__).resolve().parent.parent
VERSION_PY = REPO_ROOT / "app" / "version.py"
PYPROJECT_TOML = REPO_ROOT / "pyproject.toml"
VERSION_JSON = UPLOAD_DIR / "version.json"

VERSION_PY_RE = re.compile(r'__version__\s*=\s*"([^"]+)"')
PYPROJECT_VERSION_RE = re.compile(r'^version\s*=\s*"([^"]+)"', re.MULTILINE)


def fail(message: str) -> None:
    print(f"FEHLER: {message}", file=sys.stderr)
    sys.exit(1)


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    print(f"$ {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=REPO_ROOT, **kwargs)


def read_current_version(version_py: Path = VERSION_PY) -> str:
    match = VERSION_PY_RE.search(version_py.read_text(encoding="utf-8"))
    if not match:
        fail(f"Konnte __version__ in {version_py} nicht finden.")
    return match.group(1)


def check_git_clean() -> None:
    result = run(["git", "status", "--porcelain"], capture_output=True, text=True)
    if result.stdout.strip():
        fail(
            "Der Git-Arbeitsbaum ist nicht sauber. Bitte erst committen/stashen:\n"
            + result.stdout
        )


def validate_new_version(new_version: str, current_version: str) -> None:
    try:
        new_v = Version(new_version)
    except InvalidVersion as exc:
        fail(f"'{new_version}' ist keine gueltige SemVer-Version: {exc}")
        return
    if new_v <= Version(current_version):
        fail(f"Neue Version {new_version} muss groesser sein als die aktuelle Version {current_version}.")


def bump_version_files(new_version: str, *, version_py: Path = VERSION_PY, pyproject_toml: Path = PYPROJECT_TOML) -> None:
    version_py_text = version_py.read_text(encoding="utf-8")
    updated = VERSION_PY_RE.sub(f'__version__ = "{new_version}"', version_py_text, count=1)
    version_py.write_text(updated, encoding="utf-8")

    pyproject_text = pyproject_toml.read_text(encoding="utf-8")
    updated_pyproject = PYPROJECT_VERSION_RE.sub(f'version = "{new_version}"', pyproject_text, count=1)
    pyproject_toml.write_text(updated_pyproject, encoding="utf-8")


def git_commit_and_tag(new_version: str) -> None:
    run(["git", "add", str(VERSION_PY), str(PYPROJECT_TOML)], check=True)
    run(["git", "commit", "-m", f"Release {new_version}"], check=True)
    # Annotierter Tag (nicht "lightweight") - nur den nimmt 'git push --follow-tags' automatisch mit.
    run(["git", "tag", "-a", f"v{new_version}", "-m", f"Release {new_version}"], check=True)


def docker_build(image: str, new_version: str) -> None:
    result = run(
        ["docker", "build", "-t", f"{image}:{new_version}", "-t", f"{image}:latest", "."],
    )
    if result.returncode != 0:
        fail("Docker-Build fehlgeschlagen.")


def docker_push(image: str, new_version: str) -> None:
    for tag in (new_version, "latest"):
        result = run(["docker", "push", f"{image}:{tag}"])
        if result.returncode != 0:
            fail(
                f"Docker-Push von {image}:{tag} fehlgeschlagen. Falls es ein Auth-Fehler ist: "
                "einmalig 'docker login ghcr.io' mit einem GitHub Personal Access Token "
                "(Scope write:packages) ausfuehren - siehe README-DEPLOYMENT.md."
            )


def _parse_digest(inspect_output: str) -> str | None:
    """Extrahiert den sha256-Digest aus der Ausgabe von
    'docker inspect --format={{index .RepoDigests 0}}', z. B.
    'ghcr.io/Softlinger/ws-verlag@sha256:abc...' -> 'sha256:abc...'."""
    output = inspect_output.strip()
    if "@sha256:" not in output:
        return None
    return output.split("@", 1)[1]


def get_image_digest(image: str, new_version: str) -> str:
    result = run(
        ["docker", "inspect", "--format={{index .RepoDigests 0}}", f"{image}:{new_version}"],
        capture_output=True,
        text=True,
    )
    digest = _parse_digest(result.stdout) if result.returncode == 0 else None
    if digest is None:
        fail(
            f"Konnte den Digest von {image}:{new_version} nicht ermitteln. "
            f"Ausgabe: {result.stdout!r} {result.stderr!r}"
        )
    return digest


def write_version_json(*, new_version: str, previous_version: str, changelog: str, image: str, digest: str) -> None:
    import json

    content = {
        "version": new_version,
        "release_date": date.today().isoformat(),
        "changelog": changelog,
        "image": image,
        "image_digest": digest,
        "min_upgrade_from": previous_version,
    }
    VERSION_JSON.write_text(json.dumps(content, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Geschrieben: {VERSION_JSON}")


def ftp_upload() -> None:
    env = load_env(ENV_FILE)
    host = env["FTP_HOST"]
    user = env["FTP_USER"]
    password = env["FTP_PASSWORD"]
    remote_dir = env.get("FTP_REMOTE_DIR", "/apps/ws-verlag")

    print(f"Verbinde per FTPS zu {host} ...")
    ftps = ftplib.FTP_TLS(host, timeout=30)
    try:
        ftps.login(user=user, passwd=password)
        ftps.prot_p()
        try:
            ftps.mkd(remote_dir)
        except ftplib.error_perm:
            pass
        upload_directory(ftps, UPLOAD_DIR, remote_dir)
        print("Upload abgeschlossen.")
    finally:
        ftps.quit()


def read_current_image() -> str:
    import json

    if VERSION_JSON.exists():
        try:
            return json.loads(VERSION_JSON.read_text(encoding="utf-8"))["image"]
        except (KeyError, json.JSONDecodeError):
            pass
    return "ghcr.io/Softlinger/ws-verlag"


def main() -> None:
    parser = argparse.ArgumentParser(description="Release: Version bumpen, bauen, pushen, ausliefern.")
    parser.add_argument("new_version", help="Neue Versionsnummer, z. B. 0.2.0")
    parser.add_argument("--changelog", default=None, help="Changelog-Text fuer version.json")
    args = parser.parse_args()

    changelog = args.changelog
    if changelog is None:
        changelog = input("Changelog fuer dieses Release: ").strip()

    check_git_clean()
    previous_version = read_current_version()
    validate_new_version(args.new_version, previous_version)
    image = read_current_image()

    print(f"Release {previous_version} -> {args.new_version} (Image: {image})")

    bump_version_files(args.new_version)
    git_commit_and_tag(args.new_version)
    docker_build(image, args.new_version)
    docker_push(image, args.new_version)
    digest = get_image_digest(image, args.new_version)
    write_version_json(
        new_version=args.new_version,
        previous_version=previous_version,
        changelog=changelog,
        image=image,
        digest=digest,
    )
    ftp_upload()

    print()
    print(f"Release {args.new_version} fertig. Digest: {digest}")
    print("Noch auszufuehren: git push origin main --follow-tags")


if __name__ == "__main__":
    main()
