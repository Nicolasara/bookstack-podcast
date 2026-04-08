# TODO: Extract this hack into its own standalone repo

## Goal

Move `bookstack-hack/` out of the `bookstack-podcast` repo and into its own GitHub repository so it can be:

1. Listed on https://www.bookstackapp.com/hacks/
2. Installed via `php artisan bookstack:install-module <url>` (BookStack v26.03+)
3. Maintained independently of the bookstack-podcast service

## Suggested repo name

`Nicolasara/bookstack-podcast-hack` (or just `bookstack-podcast-hack`)

## Steps

### 1. Investigate the submission process

The official hacks list lives at https://codeberg.org/bookstack/hacks. Check:

- The `content/` directory for examples of existing hacks
- How the `mermaid-viewer` hack is structured (we already use a similar pattern)
- What metadata the hack listing page needs (description, screenshots, version compatibility)
- Whether the hack ZIP must be hosted on a specific service or anywhere works

To submit a hack, open a PR against the codeberg `hacks` repo with a new directory under `content/` containing the hack's listing metadata (likely a markdown file with frontmatter and possibly the source files).

### 2. Create the new GitHub repo

```bash
# Locally
mkdir bookstack-podcast-hack
cd bookstack-podcast-hack
git init

# Copy the hack files (without the wrapping directory)
cp /path/to/bookstack-podcast/bookstack-hack/bookstack-module.json .
cp /path/to/bookstack-podcast/bookstack-hack/functions.php .
cp -r /path/to/bookstack-podcast/bookstack-hack/views .
```

Push to a new GitHub repo: `Nicolasara/bookstack-podcast-hack`.

### 3. Add a release workflow

Create `.github/workflows/release.yml` that builds a ZIP on git tags and attaches it as a release asset:

```yaml
name: Release
on:
  push:
    tags: ['v*']

jobs:
  release:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
      - name: Build ZIP
        run: |
          ZIP_NAME="bookstack-podcast-hack-${GITHUB_REF_NAME}.zip"
          zip -r "$ZIP_NAME" bookstack-module.json functions.php views/
          echo "ZIP_NAME=$ZIP_NAME" >> $GITHUB_ENV
      - name: Create Release
        uses: softprops/action-gh-release@v2
        with:
          files: ${{ env.ZIP_NAME }}
```

After tagging `v1.0.0`, the install URL will be:
```
https://github.com/Nicolasara/bookstack-podcast-hack/releases/download/v1.0.0/bookstack-podcast-hack-v1.0.0.zip
```

### 4. Write the README

The standalone repo's README should include:

- What it does (embeds podcast player + convert buttons in BookStack pages)
- Requirements: a running [bookstack-podcast](https://github.com/Nicolasara/bookstack-podcast) service
- Install via module command:
  ```
  php artisan bookstack:install-module https://github.com/Nicolasara/bookstack-podcast-hack/releases/latest/download/bookstack-podcast-hack.zip
  ```
- Manual install (copy files to `themes/custom/modules/podcast/`)
- Required env var: `PODCAST_SERVICE_URL`
- Screenshot of the sidebar in action

### 5. Submit to the hacks list

Open a PR against https://codeberg.org/bookstack/hacks with the listing metadata. Test the install flow on a fresh BookStack instance first.

### 6. Clean up bookstack-podcast repo

Once the standalone repo is published:

- Delete `bookstack-hack/` from this repo
- Decide what to do with `bookstack-hack-link/` — likely delete it too since it just links back to the bookstack-podcast frontend (the embedded hack supersedes it)
- Update the bookstack-podcast README to link to the new hack repo instead of describing the bundled module

## Open questions

- Does `php artisan bookstack:install-module` accept GitHub release URLs directly, or does it need a specific ZIP filename / structure inside the ZIP?
- Do we need a `manifest.json` or similar at the BookStack hacks repo level for the listing to render correctly?
- Should the hack be versioned independently of the bookstack-podcast service, or kept in lockstep?
