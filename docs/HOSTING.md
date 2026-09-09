# HOSTING — how this site gets published, and how to publish another one

The site: <https://oscarsb2004.github.io/canada-economic-atlas/>

Live since 2026-09-06. GitHub Pages, built by
[`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml), free, no
account beyond GitHub and nothing to renew.

---

## The normal case: merge a reviewed pull request

`main` is the published branch. A feature-branch push runs the build check but
cannot deploy; merging its pull request into `main` is what updates the site.
Direct pushes to `main` are blocked by the checkout hook and should also be
blocked by the repository ruleset described in [`CONTRIBUTING.md`](CONTRIBUTING.md).

```bash
git switch -c feat/short-description
# make and verify the change
git push -u origin feat/short-description
```

Open the pull request, wait for its build check, then merge it. The workflow
runs `npm ci`, typechecks, builds, and publishes `web/dist` only for that merge.

### Why there is no scrape in CI

The workflow **builds** but never **pulls**. The data bundle is committed, so a
deploy is a pure build of what is already in the repo.

That is deliberate on two grounds. CI reaching out to canada.ca and StatCan on
every push would be impolite to a public service that has done nothing to
deserve it. And it would mean one commit could produce different sites on
different days, which quietly destroys the property that makes this repo
trustworthy: that what you reviewed is what shipped.

---

## Refreshing the data

```bash
python run.py          # pipeline, then verify
git switch -c data/refresh-YYYY-MM-DD
git add data/ web/public/data/
git commit -m "Refresh: <what moved>"
git push -u origin data/refresh-YYYY-MM-DD
```

Open a pull request and merge it after its build check passes. **The diff is the
review.** A run against unchanged sources produces a zero-line diff and there is
nothing to commit — that is the acceptance test for every stage, not a
coincidence. So a diff that *does* appear is a real change at the source, and it
is worth reading before opening the pull request.

Two things you will see and should not be alarmed by:

- **A revised GDP month.** StatCan revises. `release_time` beside each series is
  what tells a revision apart from a bug, which is exactly why it is stored.
- **A new `data/history/` entry.** A federal page's text changed. That is the
  mechanism working. It should never appear because *our parser* changed —
  see `verbatim_blob` in `atlas/sources/mpo.py` for why that distinction is
  enforced rather than hoped for.

---

## Redeploying without a commit

When nothing in the repo changed but you want the site rebuilt:

```bash
gh workflow run deploy.yml --ref main
```

Rarely needed. It is useful after changing a repository setting, or to confirm
the pipeline still builds from a clean checkout.

---

## Checking a deploy

```bash
gh run list -L 3
```

To watch one finish:

```bash
gh run watch $(gh run list -L 1 --json databaseId -q '.[0].databaseId') --exit-status
```

**A green check is not proof the site works.** It proves the build succeeded.
The failure mode this repo is actually exposed to — every asset 404ing under a
project-site base path — produces a green build and a blank page. Open the site
and confirm the globe draws and the KPI numbers are populated.

---

## Rolling back

Pages serves the last successful deploy, so a broken build leaves the previous
site up. If a build *succeeds* and the result is wrong:

```bash
git revert <sha>
git push
```

The revert is a push, so it deploys itself. Do not force-push `main` to fix a
site — the history is the record of what was published when, and rewriting it
makes "what did the site say in September" unanswerable.

---

## What breaks it, and how you will know

| Symptom | Cause | Fix |
|---|---|---|
| Page loads, everything blank, console full of 404s | Base path wrong | `VITE_BASE` is derived from the repo name in the workflow. If you renamed the repo, the next push fixes it by itself. |
| Build fails at `npx tsc --noEmit` | A type error | It failed *before* deploying — the live site is untouched. Fix and push. |
| Build fails at `npm ci` | `web/package-lock.json` out of step with `package.json` | Run `npm install` in `web/`, commit the lockfile. |
| Site is stale after a push | The run failed, or is still going | `gh run list -L 3` |
| Images missing, data present | Something under `web/public/media/` was not committed | `data/raw/` is gitignored; the *derived* thumbs and web sizes under `web/public/media/` are not, and must be. |

### The one that would be silent

Local builds on Windows: **Git Bash rewrites an env var whose value starts with
`/` into a Windows path**, so `VITE_BASE=/foo/ npm run build` silently produces
`/Program Files/Git/foo/`. Prefix with `MSYS_NO_PATHCONV=1`. CI runs on Linux
and is unaffected — which is why this only ever bites when you are testing a
production build by hand.

---

## Hosting the next project

`world-strategic-map` and `African-Stability-Index` are not hosted yet.
[`PROGRAM.md`](PROGRAM.md) covers the family plan; this is the mechanics.

### If it is a static site (like this one)

Copy `.github/workflows/deploy.yml` verbatim. It is repo-agnostic — `VITE_BASE`
comes from `github.event.repository.name`, so the only per-repo work is:

1. Make the repo public — Pages needs that on the Free plan.
2. `gh api -X POST repos/<owner>/<repo>/pages -f build_type=workflow`
3. Adjust `working-directory` if the app is not in `web/`.

### If it needs a server (like `African-Stability-Index`)

ASI is a Dash app; it needs a Python process, so Pages cannot host it. That is
a different problem with a different answer — a free tier on Render or Fly, or
the local launcher in `PROGRAM.md` M8. **Do not** rewrite a working server app
into a static one just to fit Pages.

### If you want the source to stay private

Pages requires a public repo on the Free plan. **Cloudflare Pages does not** —
it is free, allows private repos, and builds the same way. The cost is that
connecting it needs a browser: authorize Cloudflare on GitHub, point it at the
repo, set the build command to `npm ci && npm run build`, the output directory
to `web/dist`, and — because Cloudflare serves from the domain root rather than
a subpath — leave `VITE_BASE` unset so it defaults to `/`.

That last detail is the whole difference between the two hosts, and getting it
backwards gives a site whose assets all 404 with a green build on both.

---

## What is public

The repo is public, so all of it: the full commit history, `STATUS.md` with
every mistake this build made, `BACKLOG.md` and `PROGRAM.md`, the ~4.5 MB data
bundle and all 18 federal renderings.

There are no credentials in the repo and there never were — every source is
keyless. The federal text and imagery are Open Government Licence – Canada, with
attribution rendered in the app rather than buried in a licence file.

To reverse it: `gh repo edit --visibility private` takes the source back, **and
takes the site down with it** — Pages stops serving when a Free-plan repo goes
private. Anything cloned in the meantime stays cloned.
