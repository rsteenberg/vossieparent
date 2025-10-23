# AGENTS Guide

## Change logging policy (single source of truth)

- All functional/code changes MUST be logged in `spec.md` immediately.
- Treat `spec.md` as the authoritative blueprint for product, data model, jobs, security and rollout.
- If a change does not need a spec update, add a short "No spec impact" note in the log section.

## Required entry format in spec.md

Add a dated entry under the relevant section (e.g. Part II) with:
- Title: short description of the change
- Date: YYYY-MM-DD
- Files changed: backticked paths
- Behavior impact: what users/admins see differently
- Data model: new/changed models, migrations (yes/no)
- Integrations/Jobs: new endpoints, schedulers, tasks
- Emails/Templates: keys/paths touched
- Security/Privacy: risks, mitigations
- Rollout/Flags: enablement plan, feature flags, ops actions
- Links: commit/PR references (if available)

Example entry skeleton:

```
[2025-10-23] Notices (targeted announcements)
- Files: `content/models.py`, `content/views.py`, `jobs/tasks.py`, templates
- Behavior impact: 4-bucket announcements UI, digest email
- Data model: +Announcement.audience/severity/... (migration: yes)
- Jobs: digest context added to campaign tasks
- Templates: emails/notices_digest.{html,txt}
- Security: read receipts + permission checks per audience
- Rollout: create EmailTemplate + Campaign in admin
- Links: <commit or PR URL>
```

## When to update

- On any merged change to behavior, schema, emails, background jobs, or external integrations.
- Before handing off or ending a work session.

## PR checklist (copy into PR description)

- [ ] spec.md updated with a dated entry and affected sections
- [ ] Data model/migrations documented (if any)
- [ ] Jobs/schedules documented (if any)
- [ ] Emails/templates documented (if any)
- [ ] Security/rollout considerations captured

## Enforcement

- Until CI is added, reviewers reject PRs that lack a matching `spec.md` entry.
