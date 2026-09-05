# GitHub delivery

The integrated OpenET2 package was prepared outside the repository's earlier
task-split layout. Preserve the real repository history and do not backdate,
rewrite, or invent commits. Publish the tested snapshot through the branch and
review workflow below, then use the same workflow for every later change.

## Branch model

- `main` contains approved, release-ready work only.
- `development` is the protected integration branch.
- Every change starts from `development` on a short-lived feature branch named
  `<JIRA-KEY>-<short-kebab-description>`, for example
  `T17B-101-final-v1-6-delivery`.
- Feature branches merge into `development` by pull request.
- A release pull request merges `development` into `main`.
- Delete merged feature branches; never force-push `main` or `development`.

## Commit and pull-request policy

- Keep commits focused on one coherent change and use an imperative,
  descriptive subject prefixed by the Jira key.
- Do not combine runtime code, generated evidence, research references, and
  unrelated cleanup in one commit.
- Every pull request must include the Jira key, purpose, scope, validation
  evidence, data-safety statement, and reviewer guidance.
- Require at least one approval from a teammate other than the author.
- Dismiss stale approvals after new commits and resolve all review
  conversations before merging.
- Require the the `test` job from `offline-validation` GitHub Actions check.

The repository template and detailed contributor checklist are in
`.github/pull_request_template.md` and `CONTRIBUTING.md`.

## Required repository settings

- Protect both `main` and `development`.
- Require a pull request, one approving review, resolved conversations, and the
  the `test` job from `offline-validation` status check.
- Apply the rules to administrators so changes cannot bypass review.
- Disable force pushes and branch deletion for protected branches.
- Keep client raw data out of Git unless the client explicitly authorises it.
- Record hardware validation results in an issue or pull request and attach no
  identifiable participant data.
- Create a version tag only after the lab checklist is signed.

The CI workflow validates the offline package on Windows, runs all tests,
rebuilds the focused delay figures, and executes the synthetic multi-date
workflow. It does not claim GP3 or Tobii hardware validation.
