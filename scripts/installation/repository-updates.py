#!/usr/bin/env python3
"""Manage the opt-in macOS LaunchAgent that installs official main commits."""

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import plistlib
import re
import stat
import subprocess
import sys
import tempfile

LABEL = "local.studio.pdf-magic-repository-update"
REMOTE = "https://github.com/PDF-magic/opener.git"
BRANCH = "refs/heads/main"
PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"


def write_file(path, content):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
        staged = Path(temporary.name)
        try:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
            staged.replace(path)
        finally:
            staged.unlink(missing_ok=True)


@contextmanager
def update_lock(directory):
    directory.mkdir(parents=True, mode=0o700, exist_ok=True)
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise RuntimeError("Unsafe application update directory.")
    fd = os.open(directory / "update.lock",
                 os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise RuntimeError("Unsafe application update lock.")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def git(*args, cwd=None):
    # Fetch only from the fixed HTTPS source, without local Git URL rewrites.
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0")
    return subprocess.check_output(
        ["/usr/bin/git", "-c", "core.hooksPath=/dev/null", *args],
        cwd=cwd, env=env, text=True, timeout=180,
    ).strip()


def check_for_update(directory, app, *, interactive=False):
    executable = app / "Contents/MacOS/PDFOpener"
    if not interactive and not executable.is_file():
        print("PDF Magic Opener is missing. Open Automatic Updates to reinstall it.", flush=True)
        return
    remote = git("ls-remote", "--exit-code", REMOTE, BRANCH).split()
    if len(remote) != 2 or remote[1] != BRANCH or not re.fullmatch(r"[a-f0-9]{40}", remote[0]):
        raise RuntimeError("Could not identify the official main branch.")
    metadata_path = app / "Contents/Info.plist"
    if (executable.is_file() and metadata_path.is_file()
            and plistlib.loads(metadata_path.read_bytes()).get("PDFMagicSourceCommit") == remote[0]):
        print(f"Already installed {remote[0]}", flush=True)
        return

    with tempfile.TemporaryDirectory(prefix="source.", dir=directory) as temporary:
        checkout = Path(temporary)
        git("init", "--quiet", "--template=", cwd=checkout)
        git("fetch", "--quiet", "--no-tags", "--depth=1", REMOTE, BRANCH, cwd=checkout)
        commit = git("rev-parse", "--verify", "FETCH_HEAD^{commit}", cwd=checkout)
        git("checkout", "--quiet", "--detach", commit, cwd=checkout)
        print(f"Installing {commit}", flush=True)
        subprocess.run(
            ["/bin/bash", str(checkout / "scripts/installation/install-allow-and-open.sh")],
            cwd=checkout, check=True, stdin=None if interactive else subprocess.DEVNULL,
            env={**os.environ, "PDF_MAGIC_SOURCE_COMMIT": commit},
        )
        subprocess.run(["/usr/bin/codesign", "--verify", "--strict", str(app)], check=True)
        if plistlib.loads(metadata_path.read_bytes()).get("PDFMagicSourceCommit") != commit:
            raise RuntimeError("The installed bundle did not record the fetched commit.")
        print(f"Installed {commit}", flush=True)


def configure(home, directory, app):
    agent = home / "Library/LaunchAgents" / (LABEL + ".plist")
    domain = f"gui/{os.getuid()}"
    service = f"{domain}/{LABEL}"
    installed_script = directory / "repository-updates.py"
    arguments = [sys.executable, "-I", str(installed_script), "--check"]
    enabled = agent.is_file()
    print("Automatic updates install code from the official PDF-magic/opener main branch.")
    print("macOS checks daily at 9 a.m. local time.")
    choice = input(
        "Type DISABLE to turn off automatic updates, or press Return to exit: " if enabled else
        "Type ENABLE to install the current build and turn on automatic updates, or press Return to exit: "
    ).strip().upper()
    if choice != ("DISABLE" if enabled else "ENABLE"):
        return

    with update_lock(directory):
        if agent.is_symlink() or agent.exists() != enabled:
            raise RuntimeError("The automatic update configuration changed. Open the setup again.")
        if enabled:
            config = plistlib.loads(agent.read_bytes())
            existing = config.get("ProgramArguments", [])
            legacy = existing == ["/bin/bash", str(directory / "update.sh")]
            managed = isinstance(existing, list) and existing[1:] == arguments[1:]
            if config.get("Label") != LABEL or not (managed or legacy):
                raise RuntimeError("The existing LaunchAgent does not match PDF Magic Opener.")
            loaded = subprocess.run(
                ["/bin/launchctl", "print", service], stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if loaded.returncode == 0:
                subprocess.run(["/bin/launchctl", "bootout", service], check=True)
            agent.unlink()
            print("Automatic updates disabled.")
            return

        check_for_update(directory, app, interactive=True)
        write_file(installed_script, Path(__file__).read_bytes())
        agent.parent.mkdir(parents=True, exist_ok=True)
        log = str(directory / "update.log")
        write_file(agent, plistlib.dumps({
            "Label": LABEL,
            "ProgramArguments": arguments,
            "EnvironmentVariables": {"PATH": PATH},
            "ProcessType": "Background",
            "StartCalendarInterval": {"Hour": 9, "Minute": 0},
            "StandardOutPath": log,
            "StandardErrorPath": log,
        }))
        try:
            subprocess.run(["/bin/launchctl", "bootstrap", domain, str(agent)], check=True)
        except subprocess.CalledProcessError:
            agent.unlink()
            raise
        print("Automatic updates enabled.")


def main():
    if sys.platform != "darwin" or os.getuid() == 0:
        raise RuntimeError("Run Automatic Updates as your normal macOS user.")
    os.umask(0o077)
    home = Path.home()
    directory = home / "Library/Application Support/Studio/allow-and-open/repository-update"
    app = home / "Applications/PDF Magic Opener.app"
    if sys.argv[1:] == ["--check"] and Path(__file__).parent.resolve() == directory.resolve():
        try:
            with update_lock(directory):
                check_for_update(directory, app)
        except BlockingIOError:
            print("An application update is in progress. Retrying on the next check.", flush=True)
    elif len(sys.argv) == 1 and sys.stdin.isatty():
        configure(home, directory, app)
    else:
        raise RuntimeError("Open Automatic Updates from Finder to change your settings.")


if __name__ == "__main__":
    try:
        main()
    except EOFError:
        pass
    except BlockingIOError:
        raise SystemExit("A PDF scan or update is in progress. Open Automatic Updates again after it finishes.") from None
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        raise SystemExit(f"PDF Magic Opener automatic updates: {error}") from None
