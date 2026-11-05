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

Re-clone with the same `authors.txt` as the first migration. The commits come
out with the same hashes, so the tags attach to the existing GitHub history.
Check first with `--dry-run`:

```powershell
python .\svn-migration\svn_migration.py https://repos.curseforge.com/wow/atlas/ Atlas --stage all --dry-run
python .\svn-migration\svn_migration.py https://repos.curseforge.com/wow/atlas/ Atlas --stage all
```

The push stage leaves commits added on GitHub after the migration untouched.
It only adds the missing tags and branches.

If the old clone folder still exists, you can skip the slow clone stage. Pass
`--prefix origin/`, because the old script used git-svn's default prefix:

```powershell
python .\svn-migration\svn_migration.py https://repos.curseforge.com/wow/atlas/ Atlas --prefix origin/ --stage convert push verify
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
