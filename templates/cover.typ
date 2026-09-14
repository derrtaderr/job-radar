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
#sender("[NAME]", "[EMAIL]", "[PHONE]", "[LOCATION]")

#v(0.8em)
[DATE]

#v(0.8em)
#recipient("[HIRING MANAGER]", "[COMPANY]", "[ADDRESS]")

#v(0.8em)
Dear [HIRING MANAGER],

[PARAGRAPH ONE — why this role, why now]

[PARAGRAPH TWO — the outcome that proves fit, traced to a profile line]

[PARAGRAPH THREE — a second proof point or the org-specific angle]

[PARAGRAPH FOUR — close, call to action]

#v(0.8em)
Sincerely, \
[NAME]
