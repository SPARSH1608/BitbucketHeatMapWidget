# Bitbucket Heatmap

Generates a GitHub-style contribution heatmap from your **Bitbucket** commit
activity, so you can show real work done on a company Bitbucket workspace on
your public GitHub profile — clearly labeled as Bitbucket, not passed off as
GitHub activity.

A GitHub Action runs daily, pulls your commits from every Bitbucket
workspace/repo you're a member of, and commits `heatmap.svg`,
`heatmap-dark.svg`, and `stats.json` back into this repo. Your profile
README just points at the SVG.

## How it works

```
GitHub Action (daily cron)
   → Bitbucket API (list workspaces → repos → commits)
   → match commits by your Bitbucket account UUID
   → render heatmap.svg / heatmap-dark.svg / stats.json
   → commit + push
```

Commits are matched by Bitbucket account UUID (via `/2.0/user`), not by git
author name/email, so it works even if your local git config differs from
machine to machine.

## Setup

1. **Create an Atlassian API token** at
   [id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens)
   (app passwords are deprecated). Scope it to Bitbucket with
   `read:account:bitbucket` and `read:repository:bitbucket` (or equivalent
   read-only repo/account scopes). Auth is still basic auth — just with your
   **Atlassian account email** as the username and the token as the password.

2. **Push this repo to GitHub** (public, so the SVG can be embedded — or
   private, as long as the profile-README repo can still reach the raw URL).

3. **Add repo secrets** (Settings → Secrets and variables → Actions):
   - `BITBUCKET_EMAIL` — the email address on your Atlassian account
   - `BITBUCKET_API_TOKEN` — the API token from step 1
   - `BITBUCKET_WORKSPACES` *(optional)* — comma-separated workspace slugs to
     restrict to (e.g. `mycompany`). If omitted, all workspaces you're a
     member of are auto-discovered.

4. **Run the workflow once manually** (Actions tab → "Update Bitbucket
   Heatmap" → Run workflow) to generate the first `heatmap.svg`.

5. **Embed it in your GitHub profile README** (the special
   `<username>/<username>` repo):

   ```markdown
   ### Bitbucket Contributions

   <picture>
     <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/<you>/BitBucketHeatMap/main/heatmap-dark.svg">
     <img alt="Bitbucket contribution heatmap" src="https://raw.githubusercontent.com/<you>/BitBucketHeatMap/main/heatmap.svg">
   </picture>
   ```

   Replace `<you>` with your GitHub username.

## Notes

- The default schedule is once a day (`17 3 * * *` UTC). Adjust the cron in
  [.github/workflows/update.yml](.github/workflows/update.yml) if you want it
  fresher.
- Only commits reachable from each repo's default branch are counted (not
  every branch), to keep API usage reasonable.
- Nothing beyond the generated SVG/JSON leaves this repo — your API token
  stays in GitHub Actions secrets.
