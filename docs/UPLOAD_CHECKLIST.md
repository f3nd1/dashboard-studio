# GitHub Upload Checklist

Upload the contents of the repository root, including hidden folders such as `.github`.

Before pushing:

- Confirm the repository is private.
- Replace the placeholder email in `pyproject.toml` when appropriate.
- Confirm no `.env`, API key, password, database credential, SSH key, or production site configuration is present.
- Run `python scripts/validate_repository.py`.
- Review files under `reference/` for internal sensitivity.
- Do not upload the local Bench `sites`, `logs`, `config`, or `env` folders.

Suggested initial commit:

```text
chore: add Dashboard Studio project scaffold and migration references
```
