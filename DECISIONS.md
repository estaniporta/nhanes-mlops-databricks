# DECISIONS (Phase 0)

## Decided

### Catalog and schema
- **What:** `workspace` catalog, schema `nhanes_demo`, Volume `raw`.
- **Alternatives:** a new catalog `estani-1`; a new catalog with an underscore name.
- **Why:** fewer moving parts for a single-user demo. `estani-1` was created, then abandoned. Hyphens would also need backticks in SQL.

### Bundle variables
- **What:** `catalog` and `schema` live in `databricks.yml` as variables and reach scripts as `--catalog` / `--schema` arguments.
- **Why:** one place to rename. Rule: no literal catalog name in SQL, notebooks or CI.

### Serverless environment spec
- **What:** use `environment_version: "2"`, not `client: "1"`.
- **Why:** this workspace rejects the Client-1 channel ("Workspace doesn't support Client-1 channel for REPL"). Field names have changed across CLI versions.

### Rollback mechanism
- **What:** rollback = re-pointing the `champion` alias with `set_registered_model_alias`. No retraining, no code change.
- **Verified:** locally, and as a deployed job under my own identity. Loading via `@champion` returned different run ids after the move.
- **Test design:** `rollback_test.py` includes a fake promotion and ends in its starting state, so it can be rerun from any state. The real rollback script will not contain the fake promotion; the promote job owns that step.

### CI authentication
- **What:** OAuth M2M service principal `nhanes-ci`, secret only in GitHub Actions secrets.
- **Alternatives:** PAT as a secret (weaker, tied to my account); CI with lint/tests only and manual deploys.
- **Why:** machine identity, revocable independently of my account.
- **Verified:** `current-user me` and `bundle validate` work as the service principal.
- **Known gap:** broad API scope. Least privilege would narrow it (grants only on `workspace.nhanes_demo` and the bundle folder).

### Unity Catalog grants for the service principal
- **What:** granted `USE CATALOG` on `workspace`; `USE SCHEMA`, `CREATE MODEL`, `CREATE TABLE`, `SELECT`, `MODIFY` on `workspace.nhanes_demo`.
- **Why:** the first CI-identity run failed with "does not have USE SCHEMA". Table grants were added early because Phase 1 writes tables.

## Learned (not decisions)
- Bundle state lives in local `.databricks/` and is tied to the bundle and target, not the identity. A second identity deploying from the same folder tries to update the first identity's jobs and gets 403. Test other identities from a clean checkout, as CI does.
- An experiment path under my user folder is not readable by the service principal.
- Serverless jobs pip-install dependencies on every run, so startup is slow. The rollback job took about 1.5 min before failing.
- `get_model_version_by_alias` works; `search_model_versions(...).aliases` printed a bound method in this MLflow version.

## Open (undecided)
- **Experiment path** for jobs: `/Shared/...` with a grant, the service principal's own folder, or a bundle variable `--experiment` (leaning: variable, default under `/Shared`).
- **Model ownership:** the service principal doesn't own `dummy_model`. Grant on my model, or let CI use its own model name (leaning: own name).
- **Separate `ci` target** so CI never touches my dev jobs (leaning: yes, before Phase 4).
- **`challenger` alias after a promotion:** clear it or leave it on the promoted version.
- **Dependency pinning:** pin exact versions inline for now (mlflow, scikit-learn, from the job logs); move to a shared requirements file in Phase 1. Local MLflow versions are mismatched (3.15.2 vs 3.17.0 child packages), accepted for now.
- **Local Python env:** using conda `base`; a dedicated env was declined for now.
- **Smallest worthwhile gain:** must be logged here BEFORE any model is evaluated (Phase 1).

## Measurements still to record
- Hello job startup time; lifecycle job total time.