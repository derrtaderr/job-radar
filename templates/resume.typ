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
#contact("[NAME]", "[EMAIL]", "[PHONE]", "[LOCATION]", "[LINKS]")
= Summary
[TWO TO THREE LINES]
= Experience
#entry("[ROLE]", "[ORG]", "[DATES]")[
  - [BULLET — every claim traces to a profile line]
]
= Skills
[GROUPED SKILLS]
= Education
[DEGREE], [SCHOOL], [YEAR]
