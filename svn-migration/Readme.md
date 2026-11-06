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

## Folder layout and settings

Both scripts expect a layout like this. You can run them from any folder, e.g.
`C:\Work\GitRepos\wow-tools\svn-migration`:

```text
C:\Work\GitRepos\                  <- repos root
├── authors.txt                      <- git-svn authors file
├── wow-tools\svn-migration\         <- these scripts
├── WorldMapTrackingEnhanced\        <- local clones (new or from the old script)
├── Atlas\                           <- group folders are fine
│   ├── Atlas\
│   └── Atlas-Battle-for-Azeroth\
└── HandyNotes\
    └── HandyNotes_Argus\
```

The defaults are set at the top of `svn_migration.py`, and `svn_backfill.py`
uses the same ones:

```python
DEFAULT_REPOS_ROOT = Path(r"C:\Work\GitRepos")
AUTHORS_FILE_NAME = "authors.txt"
```

| Setting | Default | Override |
| --- | --- | --- |
| Repos root (new clones go here; old clones are looked up here) | `C:\Work\GitRepos` | `--repos-root D:\Repos` |
| Authors file | `<repos root>\authors.txt`, then `authors.txt` next to the script | `--authors D:\path\authors.txt` |

## Requirements

- Python 3.9+
- Git with `git svn` (included in Git for Windows; on Linux install `git-svn`)
- [GitHub CLI](https://cli.github.com/) (`gh`), logged in. It is only needed
  for `--create-repo`, and for the workflow guard when the commits being pushed
  contain `.github/workflows/*`. Old SVN tags usually don't, so `gh` is not
  required for them. To install on Windows:
  `winget install --id GitHub.cli`, then `gh auth login`.
- `authors.txt` in the repos root (see `authors.txt.example`). An
  `authors.txt` next to the script also works, and Git ignores it there.

## Usage

New migration (create the GitHub repo and run all stages):

```powershell
cd C:\Work\GitRepos\wow-tools\svn-migration
python .\svn_migration.py https://repos.curseforge.com/wow/world-map-tracking-enhanced/ WorldMapTrackingEnhanced --create-repo --stage all
# -> clone in C:\Work\GitRepos\WorldMapTrackingEnhanced, authors from C:\Work\GitRepos\authors.txt

# a group folder can be part of the name; the GitHub repo uses the last part
python .\svn_migration.py https://repos.curseforge.com/wow/atlas-legion/ Atlas\Atlas-Legion --stage all
# -> clone in C:\Work\GitRepos\Atlas\Atlas-Legion, pushed to github.com/arithmandar/Atlas-Legion
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
cd C:\Work\GitRepos\wow-tools\svn-migration
# preview one repo (C:\Work\GitRepos\Atlas)
python .\svn_backfill.py Atlas --dry-run
# do it
python .\svn_backfill.py Atlas
# several repos, or every git-svn clone in the repos root
python .\svn_backfill.py Atlas Atlas-Legion Atlas-Cataclysm
python .\svn_backfill.py Atlas\Atlas HandyNotes\HandyNotes_Argus
python .\svn_backfill.py --all --dry-run
python .\svn_backfill.py --all Atlas --dry-run      # only the clones under Atlas\
```

How a repo argument is resolved:

| You type | Used folder |
| --- | --- |
| `Atlas\Atlas` | `C:\Work\GitRepos\Atlas\Atlas` (path relative to the repos root) |
| `Atlas-Battle-for-Azeroth` | Searched by folder name in subfolders: `C:\Work\GitRepos\Atlas\Atlas-Battle-for-Azeroth` |
| `HandyNotes_Argus` | `C:\Work\GitRepos\HandyNotes\HandyNotes_Argus` |
| `Atlas` | `C:\Work\GitRepos\Atlas` is only a group folder, so the clone named `Atlas` inside it is used: `Atlas\Atlas` |
| `D:\Other\Clone` | Absolute paths are used as-is |

If a name matches more than one clone, the script lists them and asks you to
use the relative path. The search goes 3 levels deep and skips hidden folders
and anything inside another Git repo (e.g. `wow-tools`).

`--all` processes every git-svn clone in the repos root. `--all Atlas
HandyNotes` limits it to those group folders. With several repos, each one is
checked and confirmed separately, and a summary is printed at the end.

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
| `--all` | Process every git-svn clone in the repos root |
| `--repos-root` / `--authors` | Override the defaults above |
| `--dry-run` | Show what would happen, change nothing |
| `--svn-fetch` (`--authors FILE`) | Run `git svn fetch` first to pick up SVN revisions made after the migration |
| `--remote` / `--remote-url` | Remote or URL to push to (default: the clone's `origin`) |
| `--github-repo OWNER/NAME` | GitHub repo for the workflow guard if it can't be read from the URL (e.g. an SSH alias) |
| `--no-workflow-guard` | Do not disable workflows |
| `-y` | Skip confirmation |

If the old clone folder is gone, re-clone with `svn_migration.py` instead and
use the same `authors.txt` as the first migration so the commit hashes match:

```powershell
python .\svn_migration.py https://repos.curseforge.com/wow/atlas/ Atlas --stage all --dry-run
```

### Options

| Option | Meaning |
| --- | --- |
| `--stage clone convert push verify \| all` | Stages to run |
| `--owner` | GitHub owner (default `arithmandar`) |
| `--repos-root` | Folder for the local clone (default `C:\Work\GitRepos`; `--workdir` still works) |
| `--authors` / `--no-authors` | Authors file (default: see the settings above) |
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
- GitHub runs a push-triggered workflow from the pushed commit itself. The
  scripts check every tag and branch they are about to push. If none of those
  commits contain `.github/workflows/*`, nothing can run, so the guard is
  skipped. Otherwise they pause the repo's workflows with `gh`, or stop before
  changing anything if `gh` is missing (`--dry-run` only warns).
- On GitHub, pushing more than three tags at once does not create tag events
  either.
