// job-radar stock cover letter template (Typst). Layout above the marker, content below.
// Compile: typst compile cover.typ
#set page(paper: "us-letter", margin: (x: 1.5cm, y: 1.3cm))
#set text(font: "Libertinus Serif", size: 10.5pt)
#set par(justify: true, leading: 0.52em)
#let accent = rgb("#1a5fb4")
#let sender(name, email, phone, location) = [
  #text(size: 17pt, weight: "bold")[#name] \
  #text(size: 9.5pt, fill: accent)[#email #h(0.8em) #phone #h(0.8em) #location]
]
#let recipient(hiring_manager, company, address) = [
  #hiring_manager \
  #company \
  #address
]
// ===== CONTENT START — the /apply drafter edits ONLY below this line =====
#sender("Alex Rivera", "alex.rivera@example.com", "(303) 555-0142", "Denver, CO")

#v(0.8em)
September 13, 2026

#v(0.8em)
#recipient("Hiring Manager", "Meridian Analytics", "Denver, CO")

#v(0.8em)
Dear Hiring Manager,

I'm writing to apply for the Senior Data Engineer role at Meridian Analytics. Your team's
work building a unified reporting layer for mid-market finance teams is exactly the kind of
problem I've spent the last six years solving, and I'd like to bring that experience to
your platform.

At Northwind Analytics, I rebuilt the batch ingestion layer on a streaming architecture,
cutting data latency from six hours to under ten minutes for the finance reporting mart.
That work also included a column-level lineage tool that let analysts trace any metric back
to its source table, cutting data-trust escalations by half.

Before that, at Harborlight Data, I built the warehouse's first automated testing suite and
migrated eighteen legacy ETL jobs onto Airflow with zero missed runs during cutover. Both
roles taught me the same lesson your job posting points at directly: reliability is a
feature, not an afterthought, and it has to be built into the pipeline, not bolted on after
an outage.

I'd welcome the chance to talk about how that experience maps to Meridian Analytics' next
stage of growth. Thank you for your time and consideration.

#v(0.8em)
Sincerely, \
Alex Rivera
