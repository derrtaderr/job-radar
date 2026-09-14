// job-radar stock resume template (Typst). Layout above the marker, content below.
// Compile: typst compile resume.typ
#set page(paper: "us-letter", margin: (x: 1.5cm, y: 1.3cm))
#set text(font: "Libertinus Serif", size: 10.5pt)
#set par(justify: true, leading: 0.52em)
#let accent = rgb("#1a5fb4")
#show heading.where(level: 1): it => block(above: 0.6em, below: 0.35em)[
  #text(size: 11.5pt, weight: "bold", fill: accent, upper(it.body))
  #line(length: 100%, stroke: 0.6pt + accent)
]
#let contact(name, email, phone, location, links) = [
  #align(center)[
    #text(size: 17pt, weight: "bold")[#name] \
    #text(size: 9.5pt)[#email #h(0.8em) #phone #h(0.8em) #location #h(0.8em) #links]
  ]
]
#let entry(role, org, dates, body) = block(above: 0.55em)[
  #grid(columns: (1fr, auto),
    [*#role* — #org], text(size: 9.5pt, style: "italic")[#dates])
  #body
]
// ===== CONTENT START — the /apply drafter edits ONLY below this line =====
#contact("Alex Rivera", "alex.rivera@example.com", "(303) 555-0142", "Denver, CO", "linkedin.com/in/example")
= Summary
Data engineer with six years building pipelines that turn raw event streams into trustworthy
tables analysts actually use. Comfortable owning a data platform end to end, from ingestion
through the marts finance and product teams query daily.

= Experience
#entry("Senior Data Engineer", "Northwind Analytics", "2023 -- Present")[
  - Rebuilt the batch ingestion layer on a streaming architecture, cutting data latency from
    six hours to under ten minutes for the finance reporting mart.
  - Designed and rolled out a column-level lineage tool that let analysts trace any metric back
    to its source table, cutting data-trust escalations by half.
  - Owned the on-call rotation for the data platform, rewriting alert thresholds so paging
    volume dropped by two-thirds without missing a real incident.
]
#entry("Data Engineer", "Harborlight Data", "2019 -- 2023")[
  - Built the warehouse's first automated testing suite, catching schema drift before it
    reached downstream dashboards.
  - Migrated eighteen legacy ETL jobs off a deprecated scheduler onto Airflow with zero missed
    runs during cutover.
  - Partnered with the product team to instrument event tracking for a new feature launch,
    delivering the first usage dashboard within a week of ship.
]

= Skills
Python, SQL, Airflow, dbt, Spark, Kafka, Snowflake, AWS (S3, Redshift, Lambda), Terraform, Git

= Education
B.S. Computer Science, Ridgeline State University, 2019
