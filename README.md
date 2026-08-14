# vub-file

A fast [Ulauncher](https://ulauncher.io/) extension for finding files by name. Type `ff` in Ulauncher, then a partial filename, and matching files show up.

## Why another file-search extension?

Existing Ulauncher file-search extensions shell out to `fd`/`fzf` (or a similarly slow tool) on **every keystroke** — each query pays a fresh process spawn plus a live directory walk. `vub-file` instead builds an in-memory index once, keeps it live with filesystem watching, and treats a query as a pure in-memory scan — no subprocess, no disk walk, on every keystroke.

It has zero third-party dependencies: everything (filesystem watching, fuzzy matching) is implemented directly against the Python standard library, so the extension works the moment you add it in Ulauncher — nothing to `pip install`.

## Status

Under active development. See the repo's issues/commits for progress.

## Install

(Instructions will be added once the extension is functional — Ulauncher → Extensions → Add extension → this repo's URL.)

## License

MIT — see [LICENSE](LICENSE).
