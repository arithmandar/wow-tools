#!/usr/bin/env python3
"""Migrate a CurseForge (or any standard-layout) SVN repository to GitHub.

Unlike a plain ``git svn clone`` + ``git push --tags``, this script carries
over *everything*: trunk history, every SVN branch and every SVN tag.

Why the naive approach loses data
---------------------------------
``git svn clone --stdlayout`` imports SVN branches and tags as remote-tracking
refs (``refs/remotes/<prefix>/<branch>`` and ``refs/remotes/<prefix>/tags/<tag>``),
not as local branches or real Git tags. ``git push origin main --tags``
therefore pushes only ``main`` and zero tags. This script converts those refs
into real local branches and annotated tags before pushing them.

Stages
------
1. clone    ``git svn clone`` (or resume an interrupted clone with ``git svn fetch``)
2. convert  build ``main`` from SVN trunk, create Git branches and annotated tags
3. push     push main, branches and tags to GitHub, with GitHub Actions
            workflows temporarily disabled so old tags don't trigger releases
4. verify   compare local branches/tags with what GitHub actually has

Run ``python svn_migration.py --help`` for usage.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from urllib.parse import unquote
from dataclasses import dataclass, field
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Settings: edit these to match your machine. Command-line options override them.
# ---------------------------------------------------------------------------
# Folder that holds all local Git repositories. New SVN clones are created here
# (<repos root>\<git_name>) and svn_backfill.py looks for old clones here.
#   override: --repos-root
DEFAULT_REPOS_ROOT = Path(r"C:\Work\GitRepos")
# git-svn authors file. Searched in this order when --authors is not given:
#   <repos root>\authors.txt, then authors.txt next to this script.
#   override: --authors
AUTHORS_FILE_NAME = "authors.txt"
# ---------------------------------------------------------------------------
DEFAULT_OWNER = "arithmandar"
DEFAULT_PREFIX = "svn/"
DEFAULT_REMOTE = "github"
PUSH_CHUNK = 50  # refs per `git push`, keeps the Windows command line short

DRY_RUN = False


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
class MigrationError(RuntimeError):
    pass


def info(msg: str = "") -> None:
    print(msg, flush=True)


def warn(msg: str) -> None:
    print(f"WARNING: {msg}", flush=True)


def run(cmd: list[str], cwd: Path | None = None, *, mutate: bool = True,
        capture: bool = False, check: bool = True,
        env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """Run a command. Mutating commands are only printed in --dry-run mode."""
    shown = " ".join(f'"{c}"' if " " in c else c for c in cmd)
    if mutate and DRY_RUN:
        info(f"[dry-run] {shown}")
        return subprocess.CompletedProcess(cmd, 0, "", "")
    if not capture:
        info(f"$ {shown}")
    full_env = None
    if env:
        full_env = os.environ.copy()
        full_env.update(env)
    result = subprocess.run(cmd, cwd=cwd, env=full_env, text=True,
                            encoding="utf-8", errors="replace",
                            capture_output=capture)
    if check and result.returncode != 0:
        detail = (result.stderr or "").strip() if capture else ""
        raise MigrationError(f"Command failed ({result.returncode}): {shown}\n{detail}")
    return result


def git(repo: Path, *args: str, mutate: bool = False, check: bool = True,
        env: dict[str, str] | None = None) -> str:
    """Run git and return stdout (stripped)."""
    res = run(["git", *args], cwd=repo, mutate=mutate, capture=True,
              check=check, env=env)
    return (res.stdout or "").strip()


def ref_exists(repo: Path, ref: str) -> bool:
    if not repo.is_dir():
        return False
    return run(["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
               cwd=repo, mutate=False, capture=True, check=False).returncode == 0


def valid_ref_name(repo: Path, ref: str) -> bool:
    return run(["git", "check-ref-format", ref], cwd=repo, mutate=False,
               capture=True, check=False).returncode == 0


def chunks(items: list[str], size: int):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def confirm(question: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    return input(f"{question} (y/n): ").strip().lower() == "y"


@dataclass
class Config:
    svn_url: str
    git_name: str
    owner: str
    workdir: Path
    authors: Path | None
    prefix: str
    remote: str
    remote_url: str
    create_repo: bool
    workflow_guard: bool
    reenable_delay: int
    assume_yes: bool

    @property
    def repo(self) -> Path:
        return self.workdir / self.git_name

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.git_name}"


@dataclass
class RefPlan:
    branches: dict[str, str] = field(default_factory=dict)  # name -> sha
    tags: dict[str, str] = field(default_factory=dict)      # name -> sha (commit)


# --------------------------------------------------------------------------- #
# Stage 1: clone
# --------------------------------------------------------------------------- #
def stage_clone(cfg: Config) -> None:
    info("\n=== Stage 1: clone SVN repository ===")
    repo = cfg.repo
    if (repo / ".git" / "svn").exists():
        info(f"{repo} already contains a git-svn clone; resuming with `git svn fetch`.")
        cmd = ["git", "svn", "fetch"]
        if cfg.authors:
            cmd.append(f"--authors-file={cfg.authors}")
        run(cmd, cwd=repo)
    else:
        if repo.exists() and any(repo.iterdir()):
            raise MigrationError(f"{repo} exists and is not a git-svn clone. "
                                 "Remove it or choose another --repos-root.")
        cmd = ["git", "svn", "clone", cfg.svn_url, "--stdlayout",
               f"--prefix={cfg.prefix}"]
        if cfg.authors:
            cmd.append(f"--authors-file={cfg.authors}")
        cmd.append(str(repo))
        run(cmd, cwd=cfg.workdir)

    if DRY_RUN:
        return
    trunk = f"refs/remotes/{cfg.prefix}trunk"
    if not ref_exists(repo, trunk):
        raise MigrationError(
            f"{trunk} was not created. The SVN repository probably does not use "
            "the standard trunk/branches/tags layout.")
    summary = git(repo, "for-each-ref", "--format=%(refname)",
                  f"refs/remotes/{cfg.prefix}").splitlines()
    n_tags = sum(1 for r in summary if f"/{cfg.prefix}tags/" in r)
    info(f"Imported {len(summary)} SVN refs (trunk + {n_tags} tag refs + "
         f"{len(summary) - n_tags - 1} branch refs).")


# --------------------------------------------------------------------------- #
# Stage 2: convert
# --------------------------------------------------------------------------- #
def collect_plan(cfg: Config) -> RefPlan:
    """Work out which Git branches/tags should exist, from the SVN refs."""
    repo = cfg.repo
    base = f"refs/remotes/{cfg.prefix}"
    plan = RefPlan()
    lines = git(repo, "for-each-ref", "--format=%(refname) %(objectname)",
                base).splitlines()
    for line in lines:
        ref, sha = line.split(" ", 1)
        name = ref[len(base):]
        if name == "trunk":
            continue
        if not any((repo / ".git" / "svn" / unquote(ref)).glob(".rev_map.*")):
            # Not a git-svn ref, e.g. "origin/main" left behind by the old
            # script's `git push -u origin main` when the prefix is origin/.
            continue
        is_tag = name.startswith("tags/")
        if is_tag:
            name = name[len("tags/"):]
        if "@" in name:
            # git-svn creates "<name>@<rev>" for deleted/replaced SVN paths
            # (old incarnations). They are history noise, not real tags/branches.
            warn(f"Skipping historical git-svn ref {ref}")
            continue
        # git-svn escapes characters Git refs can't hold (e.g. space -> %20).
        # Prefer the original SVN name, else replace spaces with underscores.
        kind = "refs/tags/" if is_tag else "refs/heads/"
        for candidate in (unquote(name), unquote(name).replace(" ", "_"), name):
            if valid_ref_name(repo, kind + candidate):
                break
        else:
            warn(f"Skipping {ref}: no valid Git ref name for '{unquote(name)}'")
            continue
        if candidate != unquote(name):
            warn(f"SVN {'tag' if is_tag else 'branch'} '{unquote(name)}' imported as '{candidate}'")
        name = candidate
        if is_tag:
            plan.tags[name] = sha
        else:
            if name in ("main", "master"):
                warn(f"SVN branch '{name}' clashes with the Git default branch; "
                     f"importing it as 'svn-{name}'")
                name = f"svn-{name}"
            plan.branches[name] = sha
    return plan


def tag_target(repo: Path, sha: str) -> str:
    """An `svn copy trunk tags/x` becomes an extra commit with no file changes.
    Point the Git tag at its parent so the tag sits on the real history
    (and on the same commit GitHub already has). If the tag commit did change
    files, keep it so the tagged content is exactly what SVN had."""
    parents = git(repo, "rev-list", "--parents", "-n", "1", sha).split()[1:]
    if len(parents) == 1:
        if git(repo, "rev-parse", f"{sha}^{{tree}}") == git(repo, "rev-parse", f"{parents[0]}^{{tree}}"):
            return parents[0]
    return sha


def stage_convert(cfg: Config) -> RefPlan:
    info("\n=== Stage 2: convert SVN refs into Git branches and tags ===")
    repo = cfg.repo
    trunk = f"refs/remotes/{cfg.prefix}trunk"
    if not ref_exists(repo, trunk):
        if DRY_RUN:
            info(f"[dry-run] {trunk} does not exist yet (clone stage not run); skipping.")
            return RefPlan()
        raise MigrationError(f"{trunk} not found. Run the clone stage first.")

    # main must come from trunk. After `git svn clone`, master points to the
    # ref with the newest SVN commit, which is often a tag, not trunk.
    run(["git", "checkout", "-q", "-B", "main", trunk], cwd=repo)
    if ref_exists(repo, "refs/heads/master"):
        run(["git", "branch", "-D", "master"], cwd=repo)

    plan = collect_plan(cfg)

    for name, sha in sorted(plan.branches.items()):
        run(["git", "branch", "-f", name, sha], cwd=repo)

    created = skipped = 0
    for name, sha in sorted(plan.tags.items()):
        target = tag_target(repo, sha)
        existing = git(repo, "rev-parse", "--verify", "--quiet",
                       f"refs/tags/{name}^{{commit}}", check=False)
        if existing:
            if existing != target:
                warn(f"Local tag {name} already exists at {existing[:10]}, "
                     f"expected {target[:10]}; leaving it alone")
            skipped += 1
            plan.tags[name] = existing
            continue
        # Annotated tag that keeps the SVN tag's author, date and message.
        fmt = "%an%x00%ae%x00%aI%x00%B"
        an, ae, ad, msg = git(repo, "log", "-1", f"--format={fmt}", sha).split("\x00", 3)
        msg = msg.strip() or f"Tag {name}"
        env = {"GIT_COMMITTER_NAME": an, "GIT_COMMITTER_EMAIL": ae,
               "GIT_COMMITTER_DATE": ad}
        run(["git", "tag", "-a", name, target, "-m", msg], cwd=repo, env=env)
        plan.tags[name] = target
        created += 1

    info(f"main <- {trunk}; {len(plan.branches)} branches; "
         f"{created} tags created, {skipped} already existed.")
    return plan


def local_plan(cfg: Config) -> RefPlan:
    """Branches and tags that currently exist in the local repo."""
    repo = cfg.repo
    plan = RefPlan()
    for line in git(repo, "for-each-ref", "--format=%(refname:short) %(objectname)",
                    "refs/heads").splitlines():
        name, sha = line.split(" ", 1)
        plan.branches[name] = sha
    for line in git(repo, "for-each-ref",
                    "--format=%(refname:short) %(*objectname) %(objectname)",
                    "refs/tags").splitlines():
        name, peeled, sha = (line.split(" ") + [""])[:3]
        plan.tags[name] = peeled or sha
    return plan


# --------------------------------------------------------------------------- #
# Stage 3: push
# --------------------------------------------------------------------------- #
def gh_available() -> bool:
    return shutil.which("gh") is not None


def commits_with_workflows(repo: Path, revs: list[str]) -> list[str]:
    """Return the revs whose tree contains GitHub Actions workflow files.

    GitHub runs push-triggered workflows from the pushed commit itself, so if
    none of the pushed tags/branches contain .github/workflows/*, no workflow
    can be triggered and there is nothing to pause."""
    hits = []
    for rev in dict.fromkeys(revs):
        files = git(repo, "ls-tree", "-r", "--name-only", rev, "--", ".github/workflows",
                    check=False)
        if any(f.endswith((".yml", ".yaml")) for f in files.splitlines()):
            hits.append(rev)
    return hits


def explain_missing_gh(n_commits: int) -> str:
    return (f"{n_commits} of the commits to push contain .github/workflows, so a release "
            "workflow could run and publish old versions. The GitHub CLI (gh) is needed "
            "to pause workflows during the push.\n"
            "  Install:  winget install --id GitHub.cli   (then run: gh auth login)\n"
            "  Or pass --no-workflow-guard if you are sure nothing will be published.")


def ensure_github_repo(cfg: Config) -> None:
    if not cfg.create_repo:
        return
    if not gh_available():
        raise MigrationError("--create-repo needs the GitHub CLI (gh).")
    exists = run(["gh", "repo", "view", cfg.slug, "--json", "name"],
                 mutate=False, capture=True, check=False).returncode == 0
    if exists:
        info(f"GitHub repository {cfg.slug} already exists.")
    else:
        run(["gh", "repo", "create", cfg.slug, "--private"])


def ensure_remote(cfg: Config) -> None:
    repo = cfg.repo
    current = git(repo, "remote", "get-url", cfg.remote, check=False)
    if not current:
        run(["git", "remote", "add", cfg.remote, cfg.remote_url], cwd=repo)
    elif current != cfg.remote_url:
        warn(f"Remote '{cfg.remote}' pointed to {current}; updating to {cfg.remote_url}")
        run(["git", "remote", "set-url", cfg.remote, cfg.remote_url], cwd=repo)


def remote_refs(cfg: Config) -> tuple[dict[str, str], dict[str, str]]:
    """Return ({branch: sha}, {tag: peeled commit sha}) from the remote."""
    res = run(["git", "ls-remote", "--heads", "--tags", cfg.remote_url],
              cwd=cfg.repo, mutate=False, capture=True, check=False)
    if res.returncode != 0:
        if DRY_RUN:
            return {}, {}
        raise MigrationError(f"Cannot read {cfg.remote_url}:\n{res.stderr.strip()}")
    heads: dict[str, str] = {}
    tags: dict[str, str] = {}
    for line in res.stdout.splitlines():
        sha, ref = line.split("\t", 1)
        if ref.startswith("refs/heads/"):
            heads[ref[len("refs/heads/"):]] = sha
        elif ref.startswith("refs/tags/"):
            name = ref[len("refs/tags/"):]
            if name.endswith("^{}"):
                tags[name[:-3]] = sha          # peeled commit of annotated tag
            else:
                tags.setdefault(name, sha)
    return heads, tags


def active_workflows(cfg: Config) -> list[str]:
    res = run(["gh", "workflow", "list", "--all", "-R", cfg.slug,
               "--json", "id,name,state"], mutate=False, capture=True, check=False)
    if res.returncode != 0:
        # Repository not on GitHub yet, or no Actions: nothing to disable.
        return []
    return [str(w["id"]) for w in json.loads(res.stdout or "[]")
            if w.get("state") == "active"]


def plan_push(cfg: Config, local: RefPlan, heads: dict[str, str],
              tags: dict[str, str]) -> tuple[list[str], list[str]]:
    """Decide which refspecs to push. Never force-push."""
    repo = cfg.repo
    branch_specs: list[str] = []
    tag_specs: list[str] = []

    if heads:
        # Fetch what GitHub has so ancestry checks work.
        run(["git", "fetch", "-q", "--no-tags", cfg.remote_url,
             f"+refs/heads/*:refs/remotes/{cfg.remote}/*"], cwd=repo, mutate=False)

    for name, sha in sorted(local.branches.items(), key=lambda kv: kv[0] != "main"):
        remote_sha = heads.get(name)
        if remote_sha == sha:
            continue
        if remote_sha is None:
            branch_specs.append(f"refs/heads/{name}:refs/heads/{name}")
            continue
        is_anc = run(["git", "merge-base", "--is-ancestor", sha, remote_sha],
                     cwd=repo, mutate=False, capture=True, check=False).returncode == 0
        if is_anc:
            info(f"Branch {name}: GitHub is already ahead of the SVN import; not pushing.")
            continue
        fwd = run(["git", "merge-base", "--is-ancestor", remote_sha, sha],
                  cwd=repo, mutate=False, capture=True, check=False).returncode == 0
        if fwd:
            branch_specs.append(f"refs/heads/{name}:refs/heads/{name}")
        else:
            raise MigrationError(
                f"Branch {name} on GitHub ({remote_sha[:10]}) and the SVN import "
                f"({sha[:10]}) have unrelated or diverged history. The commits were "
                "probably rewritten differently (e.g. another authors file). "
                "Tags pushed now would not sit on GitHub's history, so stopping.")

    for name, sha in sorted(local.tags.items()):
        remote_sha = tags.get(name)
        if remote_sha is None:
            tag_specs.append(f"refs/tags/{name}:refs/tags/{name}")
        elif remote_sha != sha:
            warn(f"Tag {name} already exists on GitHub at a different commit "
                 f"({remote_sha[:10]} vs {sha[:10]}); not touching it.")
    return branch_specs, tag_specs


def stage_push(cfg: Config) -> None:
    info("\n=== Stage 3: push to GitHub ===")
    repo = cfg.repo
    if not ref_exists(repo, "refs/heads/main"):
        if DRY_RUN:
            info("[dry-run] local branch main does not exist yet; skipping.")
            return
        raise MigrationError("Local branch main not found. Run the convert stage first.")

    ensure_github_repo(cfg)
    ensure_remote(cfg)
    local = local_plan(cfg)
    heads, tags = remote_refs(cfg)
    branch_specs, tag_specs = plan_push(cfg, local, heads, tags)

    info(f"To push: {len(branch_specs)} branches, {len(tag_specs)} tags "
         f"(GitHub already has {len(heads)} branches, {len(tags)} tags).")
    if not branch_specs and not tag_specs:
        info("Nothing to push; GitHub is up to date.")
        return
    for spec in branch_specs + tag_specs:
        info(f"  {spec.split(':', 1)[0]}")
    if not confirm(f"Push these refs to {cfg.remote_url}?", cfg.assume_yes):
        info("Push cancelled.")
        return

    # Guard: disable GitHub Actions workflows (e.g. BigWigs packager on `v*`
    # tags) so importing old tags does not publish old releases to CurseForge,
    # WoWInterface or GitHub Releases.
    disabled: list[str] = []
    if cfg.workflow_guard:
        revs = [spec.split(":", 1)[0] for spec in branch_specs + tag_specs]
        risky = commits_with_workflows(repo, revs) if not DRY_RUN or ref_exists(repo, "HEAD") else []
        if not risky:
            info("None of the commits to push contain .github/workflows; "
                 "no workflow can be triggered, guard not needed.")
        elif not gh_available():
            if DRY_RUN:
                warn(explain_missing_gh(len(risky)))
            else:
                raise MigrationError(explain_missing_gh(len(risky)))
        else:
            disabled = active_workflows(cfg)
            for wf in disabled:
                run(["gh", "workflow", "disable", wf, "-R", cfg.slug])
            if disabled:
                info(f"Temporarily disabled {len(disabled)} workflow(s).")

    try:
        for group in chunks(branch_specs, PUSH_CHUNK):
            run(["git", "push", cfg.remote, *group], cwd=repo)
        if ref_exists(repo, "refs/heads/main") and not DRY_RUN:
            run(["git", "branch", "-q", "--set-upstream-to", f"{cfg.remote}/main", "main"],
                cwd=repo, check=False)
        for group in chunks(tag_specs, PUSH_CHUNK):
            run(["git", "push", cfg.remote, *group], cwd=repo)
    finally:
        if disabled:
            if not DRY_RUN and cfg.reenable_delay > 0:
                info(f"Waiting {cfg.reenable_delay}s for GitHub to process the push "
                     "events before re-enabling workflows...")
                time.sleep(cfg.reenable_delay)
            for wf in disabled:
                run(["gh", "workflow", "enable", wf, "-R", cfg.slug], check=False)
            info("Workflows re-enabled.")


# --------------------------------------------------------------------------- #
# Stage 4: verify
# --------------------------------------------------------------------------- #
def stage_verify(cfg: Config) -> bool:
    info("\n=== Stage 4: verify GitHub against the local import ===")
    if DRY_RUN:
        info("[dry-run] skipped")
        return True
    local = local_plan(cfg)
    heads, tags = remote_refs(cfg)
    missing_b = sorted(b for b in local.branches if b not in heads)
    missing_t = sorted(t for t in local.tags if t not in tags)
    diff_t = sorted(t for t, s in local.tags.items() if t in tags and tags[t] != s)
    info(f"Branches: local {len(local.branches)}, GitHub {len(heads)}, missing {len(missing_b)}")
    info(f"Tags:     local {len(local.tags)}, GitHub {len(tags)}, missing {len(missing_t)}, "
         f"different commit {len(diff_t)}")
    for b in missing_b:
        info(f"  missing branch: {b}")
    for t in missing_t:
        info(f"  missing tag:    {t}")
    for t in diff_t:
        info(f"  differs:        {t}")
    ok = not missing_b and not missing_t
    info("OK: everything from SVN is on GitHub." if ok else "INCOMPLETE: see above.")
    return ok


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
STAGES = ("clone", "convert", "push", "verify")


def default_git_name(svn_url: str) -> str:
    slug = svn_url.rstrip("/").rsplit("/", 1)[-1]
    return "-".join(part.capitalize() for part in slug.split("-")) or slug


def add_location_args(p: argparse.ArgumentParser) -> None:
    """--repos-root / --authors, shared with svn_backfill.py."""
    p.add_argument("--repos-root", "--workdir", dest="repos_root", type=Path,
                   help=f"Folder that holds your local Git repos (default: {DEFAULT_REPOS_ROOT})")
    p.add_argument("--authors", type=Path,
                   help=f"git-svn authors file (default: <repos root>\\{AUTHORS_FILE_NAME}, "
                        f"then {AUTHORS_FILE_NAME} next to this script)")


def resolve_repos_root(value: Path | None) -> Path:
    root = (value or DEFAULT_REPOS_ROOT).expanduser().resolve()
    if not root.is_dir():
        raise MigrationError(
            f"Repos root not found: {root}\n"
            "Pass --repos-root, or change DEFAULT_REPOS_ROOT at the top of svn_migration.py.")
    return root


def find_authors(value: Path | None, repos_root: Path, required: bool) -> Path | None:
    if value:
        path = value.expanduser()
        if not path.is_absolute():
            # A bare name like "authors.txt" means the one in the repos root.
            path = (Path.cwd() / path) if (Path.cwd() / path).is_file() else repos_root / path
        if not path.is_file():
            raise MigrationError(f"Authors file not found: {path}")
        return path.resolve()
    for candidate in (repos_root / AUTHORS_FILE_NAME, SCRIPT_DIR / AUTHORS_FILE_NAME):
        if candidate.is_file():
            return candidate.resolve()
    if required:
        raise MigrationError(
            f"Authors file not found in {repos_root} or {SCRIPT_DIR}.\n"
            "Create authors.txt (see authors.txt.example), pass --authors, or --no-authors.")
    return None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Migrate an SVN repository (trunk, branches and tags) to GitHub.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python svn_migration.py https://repos.curseforge.com/wow/world-map-tracking-enhanced/ "
            "WorldMapTrackingEnhanced\n"
            "  python svn_migration.py https://repos.curseforge.com/wow/atlas/ Atlas --stage convert push verify\n"
            "  python svn_migration.py https://repos.curseforge.com/wow/atlas/ Atlas --stage all --dry-run\n"
            "  python svn_migration.py https://repos.curseforge.com/wow/atlas/ Atlas --repos-root D:\\Repos\n"))
    p.add_argument("svn_url", help="SVN repository root (the folder containing trunk/branches/tags)")
    p.add_argument("git_name", nargs="?",
                   help="GitHub repository name and local folder name "
                        "(default: derived from the SVN URL)")
    p.add_argument("--stage", nargs="+", choices=STAGES + ("all",),
                   help="Stage(s) to run. Without this option you are asked interactively.")
    p.add_argument("--owner", default=DEFAULT_OWNER, help=f"GitHub owner (default: {DEFAULT_OWNER})")
    add_location_args(p)
    p.add_argument("--no-authors", action="store_true",
                   help="Clone without an authors file (SVN user names stay as-is)")
    p.add_argument("--prefix", default=DEFAULT_PREFIX,
                   help=f"git-svn ref prefix (default: {DEFAULT_PREFIX}). Use 'origin/' to "
                        "reuse an old clone made by the previous version of this script.")
    p.add_argument("--remote", default=DEFAULT_REMOTE,
                   help=f"Name of the GitHub remote in the local clone (default: {DEFAULT_REMOTE})")
    p.add_argument("--remote-url", help="Override the push URL "
                   "(default: https://github.com/<owner>/<git_name>.git)")
    p.add_argument("--create-repo", action="store_true",
                   help="Create the GitHub repository (private) with gh if it does not exist")
    p.add_argument("--no-workflow-guard", action="store_true",
                   help="Do not disable GitHub Actions workflows while pushing")
    p.add_argument("--reenable-delay", type=int, default=30,
                   help="Seconds to wait before re-enabling workflows (default: 30)")
    p.add_argument("--dry-run", action="store_true",
                   help="Print the commands that change anything instead of running them")
    p.add_argument("-y", "--yes", action="store_true", help="Do not ask for confirmation")
    return p.parse_args(argv)


def build_config(args: argparse.Namespace) -> Config:
    git_name = args.git_name or default_git_name(args.svn_url)
    prefix = args.prefix if args.prefix.endswith("/") else args.prefix + "/"
    workdir = resolve_repos_root(args.repos_root)
    authors = None if args.no_authors else find_authors(args.authors, workdir, required=True)
    return Config(
        svn_url=args.svn_url,
        git_name=git_name,
        owner=args.owner,
        workdir=workdir,
        authors=authors,
        prefix=prefix,
        remote=args.remote,
        remote_url=args.remote_url or f"https://github.com/{args.owner}/{git_name}.git",
        create_repo=args.create_repo,
        workflow_guard=not args.no_workflow_guard,
        reenable_delay=args.reenable_delay,
        assume_yes=args.yes,
    )


def choose_stages(args: argparse.Namespace) -> list[str]:
    if args.stage:
        return list(STAGES) if "all" in args.stage else [s for s in STAGES if s in args.stage]
    menu = ("=" * 80 + "\n"
            "Which stage do you want to run?\n"
            "  1: clone    git svn clone (slow; resumes if interrupted)\n"
            "  2: convert  create main, branches and tags from the SVN refs\n"
            "  3: push     push main, branches and tags to GitHub\n"
            "  4: verify   check that GitHub has every branch and tag\n"
            "  a: all      run 1-4 in order\n"
            "  You can combine stages, e.g. '234'.\n" + "=" * 80 + "\n> ")
    answer = input(menu).strip().lower()
    if answer in ("a", "all"):
        return list(STAGES)
    picked = [STAGES[int(c) - 1] for c in answer if c in "1234"]
    return [s for s in STAGES if s in picked]


def main(argv: list[str] | None = None) -> int:
    global DRY_RUN
    args = parse_args(argv)
    DRY_RUN = args.dry_run
    try:
        cfg = build_config(args)
        info(f"SVN repository : {cfg.svn_url}\n"
             f"Repos root     : {cfg.workdir}\n"
             f"Local clone    : {cfg.repo}\n"
             f"GitHub         : {cfg.remote_url}\n"
             f"Authors file   : {cfg.authors or '(none)'}\n"
             f"git-svn prefix : {cfg.prefix}")
        if not confirm("Is this correct?", cfg.assume_yes):
            info("Configuration not confirmed. Exiting.")
            return 1
        stages = choose_stages(args)
        if not stages:
            info("No stage selected. Exiting.")
            return 1
        ok = True
        for stage in stages:
            if stage == "clone":
                stage_clone(cfg)
            elif stage == "convert":
                stage_convert(cfg)
            elif stage == "push":
                stage_push(cfg)
            elif stage == "verify":
                ok = stage_verify(cfg)
        return 0 if ok else 2
    except MigrationError as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
