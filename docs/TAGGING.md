# Tag Hygiene

Safe tag push workflow. Never use `git push --tags` blindly — it can fail or clobber remote tags.

## Safe push

Use `.\tools\push_tags_safe.ps1` instead of `git push --tags`:

```powershell
.\tools\push_tags_safe.ps1
```

- Fetches tags from origin
- Pushes only tags that do **not** exist on origin
- Skips tags that already exist (no overwrite)
- Prints summary: pushed / skipped counts

## If a tag exists remotely

Do **not** attempt to overwrite. Create a new faz tag (e.g. `faz570` instead of reusing `faz569`).

## Tag patterns

The script pushes:

- `faz###` — e.g. faz569, faz567
- `fazX-stepY` — e.g. faz10-step1
