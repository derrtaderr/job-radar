---
name: Alex Rivera
email: alex.rivera@example.com
phone: (303) 555-0142
location: Denver, CO
links: linkedin.com/in/example
---

<!-- This file is the CLAIM LEDGER. The drafter may only write resume claims that trace to a line here. -->

Every bullet below is a fact about this persona's career that a resume or cover letter is
allowed to state, rephrase, or shorten. Nothing else is. A claim /apply can't trace to a
line in this file gets written as `[CONFIRM: <claim>]` and handed to you to answer — the
system never invents a skill, a number, or a job you didn't do.

Write bullets here the way you'd say them out loud to a colleague, past tense, with the
number and the thing it moved. Keep it longer than any one resume needs. A ledger with ten
years of honest material is what makes a tailored one-pager possible; a ledger trimmed to
resume length just hands the drafter the same page every time.

## Summary

Data engineer, six years, focused on pipelines that turn raw event streams into tables
analysts trust. Has owned a data platform end to end, from ingestion through the marts
finance and product query daily. Wants senior IC data or platform work, remote or Denver
metro, on a team where reliability is a stated priority rather than an after-incident one.

## Experience

### Senior Data Engineer — Northwind Analytics (2023 – Present)

- Rebuilt the batch ingestion layer on a streaming architecture, cutting data latency from
  six hours to under ten minutes for the finance reporting mart.
- Designed and rolled out a column-level lineage tool that let analysts trace any metric
  back to its source table, cutting data-trust escalations by half.
- Owned the on-call rotation for the data platform and rewrote alert thresholds, dropping
  paging volume by two-thirds without missing a real incident.
- Ran the quarterly warehouse cost review, moving cold partitions to object storage and
  holding compute spend flat across a year when query volume roughly doubled.
- Mentored two junior engineers through their first production pipeline ships, including
  code review and on-call shadowing.

### Data Engineer — Harborlight Data (2019 – 2023)

- Built the warehouse's first automated testing suite, catching schema drift before it
  reached downstream dashboards.
- Migrated eighteen legacy ETL jobs off a deprecated scheduler onto Airflow with zero
  missed runs during cutover.
- Partnered with the product team to instrument event tracking for a new feature launch,
  delivering the first usage dashboard within a week of ship.
- Wrote the team's ingestion runbook and onboarding guide, which cut new-engineer ramp on
  the pipeline stack from roughly a month to two weeks.

## Skills

- **Languages** — Python, SQL, a working amount of Scala for Spark jobs.
- **Pipelines and orchestration** — Airflow, dbt, Spark, Kafka.
- **Warehouses and storage** — Snowflake, Redshift, S3, Postgres.
- **Cloud and infrastructure** — AWS (S3, Redshift, Lambda, IAM), Terraform, Docker, Git,
  GitHub Actions.
- **Practices** — data modeling, data quality testing, lineage and observability, on-call
  and incident response, cost management.

## Education

- B.S. Computer Science, Ridgeline State University, 2019.

## Evidence notes

Context behind the numbers above, so a bullet can be restated at a different length
without drifting from what actually happened. This section is for the drafter's accuracy,
not for the resume — nothing here gets copied onto a page verbatim.

- **Six hours to under ten minutes (Northwind).** Measured as the lag between an event
  landing in the source system and appearing in the finance mart. The old pipeline ran as
  a single nightly batch plus a midday catch-up run; the replacement reads the same events
  off Kafka. Steady-state median is around seven minutes, so "under ten" is the honest
  ceiling to claim, not the average.
- **Data-trust escalations cut by half (Northwind).** Escalations were tickets where an
  analyst disputed a number and a data engineer had to trace it by hand. Roughly twenty a
  quarter before lineage shipped, roughly ten after, sustained over three quarters. The
  tool didn't fix bad data; it made tracing self-serve.
- **Paging volume down two-thirds (Northwind).** From about thirty pages a month to about
  ten, across a two-quarter comparison. The cut came from deleting alerts on metrics
  nobody acted on and adding duration thresholds to the rest. No incident in that window
  was detected late as a result, which is the part worth stating if the claim is
  challenged.
- **Compute spend flat while query volume doubled (Northwind).** Warehouse compute line
  only; storage grew. Query count roughly doubled year over year. Claim it as "held spend
  flat," never as "cut costs."
- **Eighteen ETL jobs, zero missed runs (Harborlight).** Eighteen is the exact count of
  jobs moved. Cutover ran both schedulers in parallel for two weeks and compared outputs,
  which is why the zero is verifiable rather than an impression.
- **Ramp from a month to two weeks (Harborlight).** Based on three engineers onboarded
  after the runbook versus two before, judged by when they first shipped a pipeline change
  unaided. Small sample, so this belongs in a cover letter as a story and on a resume only
  if the role explicitly asks about documentation or onboarding.
