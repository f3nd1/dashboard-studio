# Development Setup

## Assumptions

- A local or remote Frappe Bench already exists.
- The Bench version matches the target staging site.
- Development occurs on a staging site, not production.
- The GitHub repository is private.

## Option A: Clone through Bench

```bash
cd /path/to/frappe-bench
bench get-app dashboard_studio <YOUR_PRIVATE_GITHUB_REPOSITORY_URL>
bench --site <STAGING_SITE> install-app dashboard_studio
bench build --app dashboard_studio
bench --site <STAGING_SITE> migrate
bench start
```

## Option B: Repository already cloned locally

Place or clone the repository under:

```text
frappe-bench/apps/dashboard_studio
```

Then install it into the Bench environment and site using the commands appropriate to your Bench version.

## Verify installation

```bash
bench --site <STAGING_SITE> list-apps
```

Log in to Desk and confirm:

- The Dashboard Studio module is visible to System Manager.
- The Dashboard Studio page opens.
- The core DocTypes exist.
- The page health check returns successfully.

## Repository validation

```bash
python scripts/validate_repository.py
```

## Before implementation

Record:

```text
Frappe version:
ERPNext version:
Python version:
Node version:
MariaDB version:
Bench version:
Staging site name:
Hosting method:
```

Update `pyproject.toml` and implementation assumptions only after these are known.
