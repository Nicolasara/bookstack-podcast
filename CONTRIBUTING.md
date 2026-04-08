# Contributing to BookStack Podcast

Thanks for your interest in contributing! This document outlines how to get started.

## Reporting bugs

Open an issue at [github.com/Nicolasara/bookstack-podcast/issues](https://github.com/Nicolasara/bookstack-podcast/issues) with:

- A clear description of what you expected vs what happened
- Steps to reproduce
- Your environment (Docker version, BookStack version, OS)
- Relevant logs (`docker logs bookstack-podcast`)

## Suggesting features

Open an issue describing the use case. For larger changes, please discuss before opening a PR — it saves wasted work if the direction doesn't fit.

## Submitting code

1. Fork the repo and create a feature branch from `master`
2. Make your changes
3. Test locally with `docker compose up --build`
4. Sign off your commits (see DCO section below)
5. Open a pull request against `master`
6. Address any review feedback

## Developer Certificate of Origin (DCO)

This project uses the [Developer Certificate of Origin](https://developercertificate.org/). It's a simple statement that you wrote (or have the right to submit) the code you're contributing.

**You must sign off every commit** by adding a `Signed-off-by` line to your commit messages:

```
Fix podcast script generation for empty pages

Signed-off-by: Your Name <your.email@example.com>
```

The easiest way is to use the `-s` flag when committing:

```bash
git commit -s -m "your message"
```

To sign off existing commits in a branch:

```bash
git rebase --signoff master
```

PRs without DCO sign-offs will fail the automated check and cannot be merged.

## Code style

- Python: keep imports sorted, follow PEP 8 conventions
- HTML/JS: match the existing style in `app/templates/index.html`
- Keep changes focused — one logical change per PR

## Testing

Currently the project has no automated test suite. Please test manually:

1. `docker compose up --build`
2. Verify the UI loads at `http://localhost:8300`
3. Test the specific feature you changed (search, convert, settings save, etc.)
4. Check `docker logs` for errors

## License

By contributing, you agree that your contributions will be licensed under the Apache 2.0 License.
