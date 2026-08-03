<!--
One file per employer, named after the company (the importer title-cases
the filename as the company: example-startup-inc.md -> "Example Startup
Inc"). Only the text BETWEEN two headings becomes a snippet, so this
preamble — anything before the first heading below — is ignored by the
importer; it's a safe place for notes like this one.

Nest headings for readability (a "## Company" wrapper, then "###" per
role, "####" per topic) — only the LAST heading before a block of prose
actually becomes a snippet's heading. A heading immediately followed by
another heading, with nothing in between, produces no snippet at all.
-->

## Example Startup Inc.

### Senior Example Engineer

#### Platform Rebuild

Rewrote the core service layer to remove a single point of failure that
had caused two prior outages, coordinating the migration across three
dependent teams without service interruption.

- Led the technical design review and got sign-off from every downstream
  team before the first line of code changed.
- Wrote the rollback plan first, then the migration — every step was
  reversible until the final cutover.
- Cut average request latency by a third as a side effect of removing a
  synchronous call chain nobody had questioned in years.

#### Mentoring and Hiring

Built the team's technical interview loop from scratch and mentored two
junior engineers to their first promotion.

- Interviewed over forty candidates and refined the loop twice based on
  false-negative patterns noticed in later performance reviews.
- Ran a weekly pairing session that became the team's informal onboarding
  path for the next two hires.

### Example Engineer (earlier role, same company)

#### Incident Response

On-call lead for the platform's first year in production — wrote the
initial runbook and the alerting rules that later shipped as the team
standard.
