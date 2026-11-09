#!/usr/bin/env python3
"""Push the SVN tags and branches that the old migration script left behind.

Run this against the *existing* local clone that the old SVN_Migration.py
created (the folder where it ran ``git svn clone`` and
``git push -u origin main --tags``). That clone still has every SVN tag and
branch as git-svn refs, and its commits are exactly the ones already on GitHub.

What it does:

* reads the git-svn layout from the clone's config (works with the old
  ``origin/`` prefix or any other prefix),
* creates an annotated Git tag for every SVN tag that is missing,
* pushes those tags plus every SVN branch that GitHub does not have yet,
* temporarily disables GitHub Actions workflows during the push,
* checks that everything arrived.

It does NOT touch your current branch, ``main``, the working tree, or any
commit already on GitHub, and it never force-pushes. If you kept developing
in that folder, your work is safe.

Usage (run from anywhere, e.g. C:\\Work\\GitRepos\\wow-tools\\svn-migration):
    python svn_backfill.py Atlas --dry-run        # -> <repos root>\\Atlas
    python svn_backfill.py Atlas Atlas-Legion     # several clones
    python svn_backfill.py --all --dry-run        # every git-svn clone in the repos root
    python svn_backfill.py D:\\Other\\Clone        # absolute paths work too

The repos root defaults to DEFAULT_REPOS_ROOT in svn_migration.py
(C:\\Work\\GitRepos); override it with --repos-root.

Run ``python svn_backfill.py --help`` for all options.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path
from urllib.parse import unquote

import svn_migration as sm
from svn_migration import (MigrationError, chunks, confirm, git, info, run,
                           tag_target, valid_ref_name, warn)

TEMP_NS = "refs/svn-backfill/github"  # where GitHub branches are fetched for checks
PUSH_CHUNK = 50


# --------------------------------------------------------------------------- #
# Reading the old clone
# --------------------------------------------------------------------------- #
def svn_layout(repo: Path) -> tuple[str, str | None, str | None]:
    """Return the local ref patterns git-svn uses for trunk, branches and tags,
    e.g. ('refs/remotes/origin/trunk', 'refs/remotes/origin/*',
    'refs/remotes/origin/tags/*')."""
    cfg = git(repo, "config", "--get-regexp", r"^svn-remote\.svn\.", check=False)
    trunk = branches = tags = None
    for line in cfg.splitlines():
        key, _, value = line.partition(" ")
        target = value.split(":", 1)[-1]
        if key.endswith(".fetch") and target.endswith("/trunk"):
            trunk = target
        elif key.endswith(".branches"):
            branches = target
        elif key.endswith(".tags"):
            tags = target
    if not trunk:
        raise MigrationError(
            f"{repo} does not look like a git-svn clone with a standard layout "
            "(no svn-remote.svn.fetch for trunk in .git/config).")
    return trunk, branches, tags


def is_git_svn_ref(repo: Path, ref: str) -> bool:
    """True only for refs git-svn itself maintains. This filters out refs like
    refs/remotes/origin/main that `git push -u origin main` created in the
    same namespace when the git-svn prefix is origin/."""
    return any((repo / ".git" / "svn" / unquote(ref)).glob(".rev_map.*"))


def git_name_for(repo: Path, kind: str, svn_name: str) -> str | None:
    """git-svn escapes characters Git refs cannot hold (space -> %20)."""
    original = unquote(svn_name)
    for candidate in (original, original.replace(" ", "_"), svn_name):
        if valid_ref_name(repo, kind + candidate):
            if candidate != original:
                warn(f"SVN name '{original}' will be pushed as '{candidate}'")
            return candidate
    warn(f"Skipping '{original}': no valid Git ref name")
    return None


def svn_refs(repo: Path, pattern: str | None) -> dict[str, str]:
    """{full ref: commit sha} for git-svn refs matching a pattern such as
    refs/remotes/origin/tags/*. Historical "name@rev" refs are skipped."""
    if not pattern:
        return {}
    base = pattern[:-1] if pattern.endswith("*") else pattern
    out: dict[str, str] = {}
    for line in git(repo, "for-each-ref", "--format=%(refname) %(objectname)",
                    base).splitlines():
        ref, sha = line.split(" ", 1)
        if not is_git_svn_ref(repo, ref):
            continue
        if "@" in ref[len(base):]:
            info(f"  skipping historical git-svn ref {ref}")
            continue
        out[ref] = sha
    return out


# --------------------------------------------------------------------------- #
# GitHub side
# --------------------------------------------------------------------------- #
def github_slug(url: str) -> str | None:
    m = re.match(r"^(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)"
                 r"([^/]+)/(.+?)(?:\.git)?/?$", url)
    return f"{m.group(1)}/{m.group(2)}" if m else None


def remote_refs(repo: Path, url: str) -> tuple[dict[str, str], dict[str, str]]:
    res = run(["git", "ls-remote", "--heads", "--tags", url], cwd=repo,
              mutate=False, capture=True, check=False)
    if res.returncode != 0:
        raise MigrationError(f"Cannot read {url}:\n{res.stderr.strip()}")
    heads: dict[str, str] = {}
    tags: dict[str, str] = {}
    for line in res.stdout.splitlines():
        sha, ref = line.split("\t", 1)
        if ref.startswith("refs/heads/"):
            heads[ref[11:]] = sha
        elif ref.startswith("refs/tags/"):
            name = ref[10:]
            if name.endswith("^{}"):
                tags[name[:-3]] = sha
            else:
                tags.setdefault(name, sha)
    return heads, tags


def is_ancestor(repo: Path, a: str, b: str) -> bool:
    return run(["git", "merge-base", "--is-ancestor", a, b], cwd=repo,
               mutate=False, capture=True, check=False).returncode == 0


def active_workflows(slug: str) -> list[str]:
    res = run(["gh", "workflow", "list", "--all", "-R", slug, "--json", "id,state"],
              mutate=False, capture=True, check=False)
    if res.returncode != 0:
        raise MigrationError(f"Could not list workflows of {slug}:\n{res.stderr.strip()}\n"
                             "Log in with `gh auth login`, or pass --no-workflow-guard.")
    return [str(w["id"]) for w in json.loads(res.stdout or "[]") if w.get("state") == "active"]


# --------------------------------------------------------------------------- #
# Main flow
# --------------------------------------------------------------------------- #
def backfill(repo: Path, args: argparse.Namespace) -> int:
    if not (repo / ".git" / "svn").is_dir():
        raise MigrationError(f"{repo} is not a git-svn clone (.git/svn not found).")

    trunk_ref, branch_pat, tag_pat = svn_layout(repo)
    url = args.remote_url or git(repo, "remote", "get-url", args.remote, check=False)
    if not url:
        raise MigrationError(f"No remote '{args.remote}' in {repo}; pass --remote-url.")
    raw_url = git(repo, "config", "--get", f"remote.{args.remote}.url", check=False)
    slug = args.github_repo or github_slug(url) or github_slug(raw_url)

    info(f"Local clone : {repo}\n"
         f"GitHub      : {url}\n"
         f"SVN layout  : trunk={trunk_ref}  branches={branch_pat}  tags={tag_pat}")

    if args.svn_fetch:
        info("\nFetching new SVN revisions first (git svn fetch)...")
        cmd = ["git", "svn", "fetch"]
        authors = sm.find_authors(args.authors, args.repos_root, required=False)
        if authors:
            cmd.append(f"--authors-file={authors}")
        run(cmd, cwd=repo)

    # ---- collect SVN tags and branches ------------------------------------ #
    tag_base = tag_pat[:-1] if tag_pat and tag_pat.endswith("*") else (tag_pat or "")
    branch_base = branch_pat[:-1] if branch_pat and branch_pat.endswith("*") else (branch_pat or "")
    svn_tags = {ref[len(tag_base):]: sha for ref, sha in svn_refs(repo, tag_pat).items()}
    svn_branches = {
        ref[len(branch_base):]: sha for ref, sha in svn_refs(repo, branch_pat).items()
        if ref != trunk_ref and not (tag_base and ref.startswith(tag_base))
    }
    info(f"\nFound in the old clone: {len(svn_tags)} SVN tags, {len(svn_branches)} SVN branches.")

    # ---- GitHub state + safety check -------------------------------------- #
    heads, gh_tags = remote_refs(repo, url)
    if heads:
        # Fetch GitHub branches into a private namespace (never into
        # refs/remotes/origin/*, which git-svn uses in old clones).
        run(["git", "fetch", "-q", "--no-tags", url, f"+refs/heads/*:{TEMP_NS}/*"],
            cwd=repo, mutate=False)
    trunk_sha = git(repo, "rev-parse", trunk_ref)
    default = "main" if "main" in heads else next(iter(heads), None)
    if default is None:
        raise MigrationError("The GitHub repository has no branches. Use "
                             "svn_migration.py for a first-time migration instead.")
    if not is_ancestor(repo, trunk_sha, heads[default]):
        raise MigrationError(
            f"SVN trunk ({trunk_sha[:10]}) is not part of GitHub's {default} history "
            f"({heads[default][:10]}). This clone is not the one that was pushed "
            "(or history was rewritten), so its tags would not attach to GitHub's "
            "history. Stopping.")
    info(f"Check OK: GitHub '{default}' contains SVN trunk {trunk_sha[:10]}.")

    # ---- plan tags -------------------------------------------------------- #
    tags_to_create: list[tuple[str, str, str]] = []   # (git name, target, svn sha)
    tag_specs: list[str] = []
    for svn_name, sha in sorted(svn_tags.items()):
        name = git_name_for(repo, "refs/tags/", svn_name)
        if not name:
            continue
        target = tag_target(repo, sha)
        local = git(repo, "rev-parse", "--verify", "--quiet", f"refs/tags/{name}^{{commit}}",
                    check=False)
        remote = gh_tags.get(name)
        if remote:
            if remote != target and remote != sha:
                warn(f"Tag {name} already on GitHub at {remote[:10]} (SVN: {target[:10]}); leaving it")
            continue
        if local and local != target:
            warn(f"Local tag {name} points to {local[:10]}, SVN tag is {target[:10]}; "
                 "pushing the local tag as-is")
        if not local:
            tags_to_create.append((name, target, sha))
        tag_specs.append(f"refs/tags/{name}:refs/tags/{name}")

    # ---- plan branches ---------------------------------------------------- #
    branch_specs: list[str] = []
    for svn_name, sha in sorted(svn_branches.items()):
        name = git_name_for(repo, "refs/heads/", svn_name)
        if not name:
            continue
        if name in ("main", "master"):
            name = f"svn-{name}"
        remote = heads.get(name)
        if remote is None:
            branch_specs.append(f"{sha}:refs/heads/{name}")
        elif remote != sha and not is_ancestor(repo, sha, remote):
            warn(f"Branch {name} already on GitHub with different history; leaving it")

    info(f"\nGitHub already has {len(heads)} branches and {len(gh_tags)} tags.")
    info(f"To push: {len(tag_specs)} tags, {len(branch_specs)} branches.")
    for spec in tag_specs:
        info(f"  tag    {spec.split(':')[0][10:]}")
    for spec in branch_specs:
        info(f"  branch {spec.split(':')[1][11:]}")
    # ---- does anything we push contain workflow files? ------------------- #
    guard = False
    if tag_specs or branch_specs:
        revs = [t for _, t, _ in tags_to_create]
        revs += [git(repo, "rev-parse", f"{s.split(':')[0]}^{{commit}}") for s in tag_specs
                 if not any(s == f"refs/tags/{n}:refs/tags/{n}" for n, _, _ in tags_to_create)]
        revs += [s.split(":")[0] for s in branch_specs]
        risky = sm.commits_with_workflows(repo, revs)
        if not risky:
            info("\nNone of the commits to push contain .github/workflows; no workflow "
                 "can be triggered, so the workflow guard is not needed (gh not required).")
        elif args.no_workflow_guard:
            warn(f"{len(risky)} commit(s) to push contain workflow files, and "
                 "--no-workflow-guard was given.")
        else:
            problem = None
            if not slug:
                problem = (f"{len(risky)} commit(s) to push contain .github/workflows, but "
                           f"{url} is not recognised as a GitHub repository, so workflows "
                           "cannot be paused. Pass --github-repo owner/name, or "
                           "--no-workflow-guard.")
            elif shutil.which("gh") is None:
                problem = sm.explain_missing_gh(len(risky))
            if problem and sm.DRY_RUN:
                warn(problem)
            elif problem:
                raise MigrationError(problem)
            else:
                guard = True
                info(f"\n{len(risky)} commit(s) contain workflow files; workflows on {slug} "
                     "will be paused during the push.")

    if not tag_specs and not branch_specs:
        info("\nNothing to do: GitHub already has every SVN tag and branch.")
        cleanup(repo)
        return 0
    if not confirm(f"\nCreate the missing tags locally and push to {url}?", args.yes):
        info("Cancelled.")
        cleanup(repo)
        return 1

    # ---- create annotated tags (keeps SVN author/date/message) ------------ #
    for name, target, sha in tags_to_create:
        an, ae, ad, msg = git(repo, "log", "-1", "--format=%an%x00%ae%x00%aI%x00%B",
                              sha).split("\x00", 3)
        run(["git", "tag", "-a", name, target, "-m", msg.strip() or f"Tag {name}"],
            cwd=repo, env={"GIT_COMMITTER_NAME": an, "GIT_COMMITTER_EMAIL": ae,
                           "GIT_COMMITTER_DATE": ad})
    if tags_to_create and not sm.DRY_RUN:
        info(f"Created {len(tags_to_create)} local tags.")

    # ---- push with workflows disabled ------------------------------------- #
    disabled: list[str] = []
    if guard:
        disabled = active_workflows(slug)
        for wf in disabled:
            run(["gh", "workflow", "disable", wf, "-R", slug])
        if disabled:
            info(f"Temporarily disabled {len(disabled)} workflow(s) on {slug}.")
    try:
        for group in chunks(branch_specs, PUSH_CHUNK):
            run(["git", "push", url, *group], cwd=repo)
        for group in chunks(tag_specs, PUSH_CHUNK):
            run(["git", "push", url, *group], cwd=repo)
    finally:
        if disabled:
            if not sm.DRY_RUN and args.reenable_delay > 0:
                info(f"Waiting {args.reenable_delay}s before re-enabling workflows...")
                time.sleep(args.reenable_delay)
            for wf in disabled:
                run(["gh", "workflow", "enable", wf, "-R", slug], check=False)
            info("Workflows re-enabled.")

    # ---- verify ----------------------------------------------------------- #
    cleanup(repo)
    if sm.DRY_RUN:
        info("\n[dry-run] nothing was changed.")
        return 0
    heads, gh_tags = remote_refs(repo, url)
    missing_t = [s.split(":")[1][10:] for s in tag_specs if s.split(":")[1][10:] not in gh_tags]
    missing_b = [s.split(":")[1][11:] for s in branch_specs if s.split(":")[1][11:] not in heads]
    info(f"\nVerify: GitHub now has {len(gh_tags)} tags and {len(heads)} branches.")
    for t in missing_t:
        info(f"  missing tag:    {t}")
    for b in missing_b:
        info(f"  missing branch: {b}")
    if missing_t or missing_b:
        info("INCOMPLETE: see above.")
        return 2
    info("OK: every SVN tag and branch is on GitHub.")
    return 0


def cleanup(repo: Path) -> None:
    for ref in git(repo, "for-each-ref", "--format=%(refname)", TEMP_NS).splitlines():
        run(["git", "update-ref", "-d", ref], cwd=repo, mutate=False, capture=True, check=False)


SCAN_DEPTH = sm.SCAN_DEPTH
is_svn_clone = sm.is_svn_clone
scan_clones = sm.scan_clones
same_name = sm.same_name


def resolve_repo(name: Path, root: Path, clones: list[Path] | None) -> tuple[Path, list[Path] | None]:
    """Resolve a repo argument:
    1. absolute path, or a path under the repos root (Atlas\\Atlas), if it is a clone
    2. otherwise a clone with that folder name anywhere under the repos root
       (Atlas -> GitRepos\\Atlas\\Atlas, HandyNotes_Argus -> GitRepos\\HandyNotes\\HandyNotes_Argus)
    """
    path = name.expanduser()
    direct = path if path.is_absolute() else root / path
    if is_svn_clone(direct) or path.is_absolute():
        return direct.resolve(), clones
    if clones is None:
        clones = scan_clones(root)
    leaf = path.name
    matches = [c for c in clones if same_name(c.name, leaf)]
    if len(matches) == 1:
        if matches[0].resolve() != direct.resolve():
            info(f"{name} -> {matches[0]}")
        return matches[0].resolve(), clones
    if len(matches) > 1:
        options = "\n  ".join(str(m.relative_to(root)) for m in matches)
        raise MigrationError(f"'{name}' matches several clones; use the full relative path:\n  {options}")
    hint = ""
    if direct.is_dir():
        inside = scan_clones(direct)
        if inside:
            hint = (f"\n{direct} is a folder with {len(inside)} clone(s); to process all of them use:"
                    f"\n  python svn_backfill.py --all {name}")
    raise MigrationError(f"No git-svn clone named '{name}' found under {root}.{hint}")


def find_repos(args: argparse.Namespace) -> list[Path]:
    root: Path = args.repos_root
    if args.all:
        # `--all` alone: whole repos root. `--all Atlas HandyNotes`: only those folders.
        scopes = []
        for name in args.repos or [Path(".")]:
            scope = name.expanduser()
            scope = scope if scope.is_absolute() else root / scope
            if not scope.is_dir():
                raise MigrationError(f"Folder not found: {scope}")
            scopes.append(scope.resolve())
        found = list(dict.fromkeys(c.resolve() for s in scopes for c in scan_clones(s)))
        if not found:
            raise MigrationError(f"No git-svn clones found in {', '.join(map(str, scopes))}.")
        info(f"Found {len(found)} git-svn clone(s):")
        for c in found:
            info(f"  {c.relative_to(root) if c.is_relative_to(root) else c}")
        return found
    if not args.repos:
        if is_svn_clone(Path.cwd()):
            return [Path.cwd()]
        raise MigrationError("Give one or more repo names (folders in "
                             f"{root}), a path, or --all.")
    out: list[Path] = []
    clones: list[Path] | None = None
    for name in args.repos:
        repo, clones = resolve_repo(name, root, clones)
        out.append(repo)
    return list(dict.fromkeys(out))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Push missing SVN tags/branches from old git-svn clones to GitHub.",
        epilog="Examples:\n"
               "  python svn_backfill.py Atlas --dry-run\n"
               "  python svn_backfill.py Atlas Atlas-Legion Atlas-Cataclysm\n"
               "  python svn_backfill.py Atlas\\Atlas HandyNotes\\HandyNotes_Argus\n"
               "  python svn_backfill.py --all --dry-run           (whole repos root)\n"
               "  python svn_backfill.py --all Atlas HandyNotes    (only these folders)\n"
               "  python svn_backfill.py Atlas --repos-root D:\\Repos",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("repos", type=Path, nargs="*",
                   help="Old clone(s): a folder name (searched in subfolders too, e.g. "
                        "Atlas-Legion finds Atlas\\Atlas-Legion), a path relative to the "
                        "repos root (Atlas\\Atlas), or an absolute path. With --all: the "
                        "folders to search")
    p.add_argument("--all", action="store_true",
                   help=f"Process every git-svn clone in the repos root (or in the given "
                        f"folders), up to {SCAN_DEPTH} levels deep")
    sm.add_location_args(p)
    p.add_argument("--remote", default="origin",
                   help="Remote that points to GitHub in that clone (default: origin)")
    p.add_argument("--remote-url", help="Push to this URL instead of the remote's URL "
                   "(only with a single repo)")
    p.add_argument("--github-repo", metavar="OWNER/NAME",
                   help="GitHub repository for the workflow guard, if it can't be read "
                        "from the remote URL (only with a single repo)")
    p.add_argument("--svn-fetch", action="store_true",
                   help="Run `git svn fetch` first to pick up SVN revisions made after the "
                        "original migration (uses the authors file)")
    p.add_argument("--no-workflow-guard", action="store_true",
                   help="Do not disable GitHub Actions workflows while pushing")
    p.add_argument("--reenable-delay", type=int, default=30,
                   help="Seconds to wait before re-enabling workflows (default: 30)")
    p.add_argument("--dry-run", action="store_true",
                   help="Show what would be created and pushed, change nothing")
    p.add_argument("-y", "--yes", action="store_true", help="Do not ask for confirmation")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    sm.DRY_RUN = args.dry_run
    try:
        args.repos_root = sm.resolve_repos_root(args.repos_root)
        repos = find_repos(args)
        if len(repos) > 1 and (args.remote_url or args.github_repo):
            raise MigrationError("--remote-url / --github-repo only work with a single repo.")
    except MigrationError as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 1

    results: dict[str, str] = {}
    for repo in repos:
        label = str(repo.relative_to(args.repos_root)) if repo.is_relative_to(args.repos_root) else str(repo)
        if len(repos) > 1:
            info("\n" + "=" * 78 + f"\n{label}\n" + "=" * 78)
        try:
            code = backfill(repo, args)
            results[label] = {0: "OK", 1: "cancelled", 2: "INCOMPLETE"}.get(code, str(code))
        except MigrationError as exc:
            print(f"\nERROR ({label}): {exc}", file=sys.stderr)
            results[label] = "ERROR"
        except KeyboardInterrupt:
            print("\nInterrupted.", file=sys.stderr)
            return 130
    if len(repos) > 1:
        info("\nSummary:")
        for name, status in results.items():
            info(f"  {status:<10} {name}")
    return 0 if all(v == "OK" for v in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
