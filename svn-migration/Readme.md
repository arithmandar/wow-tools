# SVN to GitHub migration

`svn_migration.py` moves a CurseForge (or any standard trunk/branches/tags)
SVN repository to GitHub with trunk history, every SVN branch and every SVN
tag.

## Why the old version lost tags and branches

`git svn clone --stdlayout` stores SVN branches and tags as remote-tracking refs
(`refs/remotes/<prefix>/<branch>`, `refs/remotes/<prefix>/tags/<tag>`). They are
not local branches or real Git tags, so `git push -u origin main --tags` pushed
only `main` and no tags. The old script also renamed whatever `master` pointed
to. After `git svn clone`, `master` points to the ref with the newest SVN
commit, which can be a tag instead of trunk.

## What the script does

| Stage | What happens |
| --- | --- |
| 1 `clone` | `git svn clone --stdlayout --prefix=svn/`. If the folder already has a clone, it resumes with `git svn fetch`. |
| 2 `convert` | Creates `main` from `svn/trunk` and deletes `master`. Creates a Git branch for each SVN branch. Creates an annotated tag for each SVN tag that keeps the SVN author, date and message. A tag created by a plain `svn copy` points at the trunk commit it copied, so it sits on `main`'s history. Skips `name@rev` refs, which are deleted or replaced SVN paths. |
| 3 `push` | Pushes only what GitHub is missing and never force-pushes. Stops if GitHub's `main` and the import have unrelated history. Skips tags that already exist at a different commit. Before pushing to an existing repo, it disables active GitHub Actions workflows (e.g. the BigWigs packager on `v*` tags) and re-enables them afterwards. |
| 4 `verify` | Compares local branches and tags with `git ls-remote` on GitHub and lists anything missing. |

Every stage can be run again safely.

## Requirements

- Python 3.9+
- Git with `git svn` (included in Git for Windows; on Linux install `git-svn`)
- [GitHub CLI](https://cli.github.com/) (`gh`), logged in. Needed for the
  workflow guard and `--create-repo`.
- `authors.txt` next to the script (copy `authors.txt.example`). Git ignores
  this file.

## Usage

New migration (create the GitHub repo and run all stages):

```powershell
python .\svn-migration\svn_migration.py https://repos.curseforge.com/wow/world-map-tracking-enhanced/ WorldMapTrackingEnhanced --create-repo --stage all
```

Without `--stage` the script asks which stages to run (`1`-`4`, combinations
like `234`, or `a` for all). `git_name` defaults to a name derived from the SVN
URL.

### Adding missing tags to a repo migrated with the old script

Use `svn_backfill.py`, and run it against the old local clone, i.e. the folder
where the old `SVN_Migration.py` ran `git svn clone` and `git push`. That clone
still has every SVN tag and branch as git-svn refs. Its commits are exactly the
ones on GitHub, so no authors file or re-clone is needed.

```powershell
# 1. preview: lists the tags/branches that would be created and pushed
python .\svn-migration\svn_backfill.py D:\path\to\Atlas --dry-run
# 2. do it
python .\svn-migration\svn_backfill.py D:\path\to\Atlas
```

`svn_backfill.py` imports helpers from `svn_migration.py`, so keep both files
in the same folder.

What it does:

- Reads the git-svn layout from the clone's `.git/config` (the old script used
  the `origin/` prefix).
- Stops if SVN trunk is not part of GitHub's `main` history, which would mean
  the folder is not the clone that was pushed.
- Creates annotated tags for the missing SVN tags and pushes them along with
  any SVN branches GitHub doesn't have. GitHub Actions workflows are disabled
  during the push.
- Checks GitHub afterwards.

It leaves your current branch, `main`, the working tree and existing GitHub
commits alone, and never force-pushes. Commits you made in that folder after
the migration are safe. GitHub branches are fetched into a private
`refs/svn-backfill/` namespace, which is deleted afterwards, so the git-svn
refs under `refs/remotes/origin/` are not affected.

| Option | Meaning |
| --- | --- |
| `--dry-run` | Show what would happen, change nothing |
| `--svn-fetch` (`--authors FILE`) | Run `git svn fetch` first to pick up SVN revisions made after the migration |
| `--remote` / `--remote-url` | Remote or URL to push to (default: the clone's `origin`) |
| `--github-repo OWNER/NAME` | GitHub repo for the workflow guard if it can't be read from the URL (e.g. an SSH alias) |
| `--no-workflow-guard` | Do not disable workflows |
| `-y` | Skip confirmation |

If the old clone folder is gone, re-clone with `svn_migration.py` instead and
use the same `authors.txt` as the first migration so the commit hashes match:

```powershell
python .\svn-migration\svn_migration.py https://repos.curseforge.com/wow/atlas/ Atlas --stage all --dry-run
```

### Options

| Option | Meaning |
| --- | --- |
| `--stage clone convert push verify \| all` | Stages to run |
| `--owner` | GitHub owner (default `arithmandar`) |
| `--workdir` | Folder for the local clone (default: current folder) |
| `--authors` / `--no-authors` | Authors file (default `authors.txt` next to the script) |
| `--prefix` | git-svn ref prefix (default `svn/`) |
| `--remote` / `--remote-url` | Remote name (default `github`) and push URL override |
| `--create-repo` | Create the GitHub repo (private) if it does not exist |
| `--no-workflow-guard` | Do not disable workflows while pushing |
| `--reenable-delay` | Seconds to wait before re-enabling workflows (default 30) |
| `--dry-run` | Print the commands that change anything instead of running them |
| `-y`, `--yes` | Skip confirmations |

## Notes

- The GitHub remote is called `github`, not `origin`, so it never mixes with
  git-svn refs.
- If `git svn` reports `Author: xxx not defined in authors.txt`, add the user
  and run the `clone` stage again. It resumes from where it stopped.
- On GitHub, pushing more than three tags at once does not trigger tag
  workflows. Tags whose commit has no workflow file don't trigger them either.
  The workflow guard is an extra safety layer on top of this.
