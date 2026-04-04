# Release Checklist

Pre-release steps for BIST Elite Core.

---

## 1. Git status clean

```powershell
git status --porcelain
```

No uncommitted changes. Stash or commit before release.

---

## 2. Clean repo + proof pack

```powershell
.\tools\clean_repo.ps1
.\tools\proof_pack.ps1
```

Or use aliases: `. .\tools\aliases.ps1` then `run_proof`.

---

## 3. Full pytest

```powershell
python -m pytest -q tests/
```

Exit code 0 required.

---

## 4. Push main

```powershell
git push origin main
```

---

## 5. Tag (optional)

```powershell
git tag -a v1.2.3 -m "Release v1.2.3"
git push origin v1.2.3
```

Use semantic versioning. Tags are immutable; create a new tag for corrections.
