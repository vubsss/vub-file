# vub-file

A fast [Ulauncher](https://ulauncher.io/) extension for finding files by name. Type `ff` in Ulauncher, then a partial filename, and matching files show up.

## Why another file-search extension?

Existing Ulauncher file-search extensions shell out to `fd`/`fzf` (or a similarly slow tool) on **every keystroke** — each query pays a fresh process spawn plus a live directory walk. `vub-file` instead builds an in-memory index once, keeps it live with filesystem watching, and treats a query as a pure in-memory scan — no subprocess, no disk walk, on every keystroke.

It has zero third-party dependencies: everything (filesystem watching, fuzzy matching) is implemented directly against the Python standard library, so the extension works the moment you add it in Ulauncher — nothing to `pip install`.

## Install

1. Open Ulauncher's preferences → **Extensions** → **Add extension**.
2. Paste this repo's URL: `https://github.com/vubsss/vub-file`.
3. Type `ff` followed by a space and a partial filename.

The first time it runs, `vub-file` indexes your search roots (`~` by default) in the background — search results start appearing immediately from the on-disk cache (empty on the very first run) and get more complete as indexing finishes. Every run after that loads instantly from the cache in `~/.cache/vub-file/index.db`.

## Opening results

| Key | Action |
| --- | --- |
| <kbd>Enter</kbd> | Open your file manager at the file's folder, with the file selected. |
| <kbd>Alt</kbd>+<kbd>Enter</kbd> | Open the file itself in its default application. |

Selecting the file needs a file manager implementing the freedesktop.org `org.freedesktop.FileManager1` D-Bus interface — Nautilus, Dolphin, Nemo, Thunar and PCManFM all do, and it's started automatically if it isn't already running. On desktops without it, <kbd>Enter</kbd> falls back to `xdg-open` on the folder, which opens the right directory but can't highlight the file.

## Preferences

| Preference | Default | Description |
| --- | --- | --- |
| Find files (keyword) | `ff` | The keyword that triggers the extension. |
| Search roots | `~` | Comma-separated list of directories to index. |
| Max results | `8` | Maximum number of results shown per query. |
| Ignore hidden files | on | Skip dotfiles and dot-directories (in addition to the built-in ignore list: `.git`, `node_modules`, `__pycache__`, `venv`, `build`, `dist`, etc). |

You can add your own ignore patterns (gitignore-style: plain names, `*` wildcards, trailing `/` for directory-only, leading `/` to anchor to a search root, `!` to re-include) in `~/.vub-file-ignore`.

## Troubleshooting

**Some files inside a large directory tree (e.g. a big monorepo) aren't updating live.** This usually means the kernel's inotify watch limit was hit — `vub-file` puts one watch per indexed directory, and the default `fs.inotify.max_user_watches` on some distros is too low for very large trees. The affected directories fall back to polling automatically (so they still update, just every ~30s instead of instantly) and a warning is logged. To fix it properly, raise the limit:

```sh
echo fs.inotify.max_user_watches=524288 | sudo tee -a /etc/sysctl.d/99-vub-file.conf
sudo sysctl --system
```

Then restart Ulauncher (or just wait — the extension retries watching automatically as space frees up).

## Development

```sh
pip install ruff pytest
ruff check .
pytest
```

Everything under `lib/` is plain Python with no Ulauncher dependency, so it's fully unit-testable on its own — see `tests/`. `main.py` is the thin glue layer to Ulauncher's extension API; since Ulauncher itself is a GTK desktop app that can't run headless, `tests/test_main_smoke.py` exercises `main.py` against a minimal stand-in for the `ulauncher` package instead. Real end-to-end verification (does search actually feel instant, does the watcher pick up live changes, etc.) needs an actual Ulauncher install.

## Status

Under active development. See the repo's issues/commits for progress.

## License

MIT — see [LICENSE](LICENSE).
