# CONTRIBUTING — safe change and release flow

`main` is the published history. A push to it deploys the GitHub Pages site, so
do all work on a feature branch and merge it through a pull request.

## One-time checkout setup

```bash
npm run setup-git-safety
```

This activates the versioned `.githooks/pre-push` guard for this checkout. It
blocks a direct `git push origin main`; it does not interfere with normal branch
pushes. Git hooks are local and can be bypassed, so GitHub branch protection is
still required for the actual remote lock.

## Normal change flow

```bash
git switch -c feat/short-description
# make and verify the change
git add <specific files>
git commit -m "Describe the change"
git push -u origin feat/short-description
```

Open a pull request from `feat/short-description` into `main`. GitHub Actions
will build the app for the pull request without deploying it. Merge the pull
request only after the check is green; that merge is the only change that
deploys Pages.

Avoid `git add -A` for routine work: this repository has generated data and
build metadata, so stage the files you reviewed by name.

## GitHub repository setting (owner, once)

In **Settings → Branches → Add branch ruleset**, target `main` and enable:

- Require a pull request before merging
- Require the `Build (and deploy to Pages on demand) / build` status check
- Block force pushes and branch deletion

The local hook protects your own checkout; the ruleset protects the repository
regardless of who or what tries to push.
