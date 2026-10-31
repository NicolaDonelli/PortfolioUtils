---
name: conventional-commit
description: Write and create git commits that pass the PortfolioUtils commitlint and pre-commit hooks (conventional commits, allowed types, English, description ending with a period, detect-secrets). Use when asked to commit changes, write a commit message or prepare changes for a push.
argument-hint: "[optional scope or summary]"
---
# Conventional commit

## Format (enforced by `.commitlintrc.yaml` and the README rules)

```
<type>(<optional scope>)<optional !>: <description ending with a period.>

<optional body in English, after one blank line>

<optional footers, after one blank line: Refs: #12 / BREAKING CHANGE: ...>
```

- Types: `fix`, `feat`, `doc`, `perf`, `refactor`, `style`, `test`, `chore`
  (note: `doc`, not `docs`; there is no `ci` or `build` type, use `chore(ci)`).
- Scopes used here: `download`, `analysis`, `settings`, `storage`, `deps`, `ci`, `docs`,
  `devcontainer`, `copilot`.
- Description: imperative, English, ends with `.`.
- `chore` commits are skipped by git-cliff in the changelog: use `feat`/`fix`/`perf`/
  `refactor` for anything a user of the library would notice.

## Procedure

1. Inspect what will be committed: `git status` and `git diff --staged`.
   Never stage `.env`, files in `data/` or generated `requirements/*.txt`.
2. Split unrelated changes into separate commits (`git add -p`).
3. Write the message to a temporary file to keep blank lines intact, then commit:
   ```bash
   msg_file="$(mktemp)"
   cat > "$msg_file" <<'MSG'
   feat(download): add incremental update of historical prices.

   Read the last stored date and request only newer rows, then merge and
   deduplicate before an atomic write.
   MSG
   git commit -F "$msg_file" && rm -f "$msg_file"
   ```
4. If commitlint or detect-secrets fails, fix the message or remove the secret and commit
   again. Never use `--no-verify`.
5. Do not push unless asked. `git push` triggers `make checks` through the pre-push hook.

## Examples

- `feat(analysis): add Ledoit-Wolf shrinkage for covariance estimation.`
- `fix(storage): keep the newest value when merging duplicated dates.`
- `test(download): cover retry on HTTP 429 responses.`
- `chore(deps): add curl_cffi for Cloudflare-compatible requests.`
- `doc: describe the CSV schema in the user guide.`
