// Two-column resume, one page.
//
// This file is layout only. Every fact it renders arrives as data — there is no
// person in here. scripts/generate_resume.py merges profile.yaml with a role
// config and passes the result as compact JSON:
//
//     typst compile resume.typ out.pdf --input data='{"identity":{...},...}'
//
// To preview without the generator, hand it any JSON of the same shape.

#let data = json(bytes(sys.inputs.at("data", default: "{}")))

#let identity = data.at("identity", default: (:))
#let jobs = data.at("experience", default: ())
#let certifications = data.at("certifications", default: ())
#let education = data.at("education", default: ())

// Colors
#let accent = rgb("#1a73b8")
#let gray = rgb("#666666")
#let lightgray = rgb("#888888")

#set page(
  paper: "us-letter",
  margin: (top: 0.3in, bottom: 0.3in, left: 0.35in, right: 0.35in),
)

// Helvetica Neue is macOS-only; the rest of the chain covers Windows. On Linux
// none of these exist and Typst falls back to a bundled font with a warning —
// it still compiles, the PDF just isn't identical.
#set text(
  font: ("Helvetica Neue", "Helvetica", "Arial"),
  size: 9pt,
  fill: rgb("#333333"),
)
#set par(leading: 0.45em)

// This layout is designed for a single page, and overflow is quiet — a stray
// half-line pushes one orphan onto page two, which looks worse than either a
// tight page or an honest two-pager. Publishing the final count lets the
// generator warn instead of leaving you to notice in a PDF viewer.
#context [#metadata(counter(page).final().first()) <page-count>]

#let sidebar-heading(content) = {
  text(size: 8pt, weight: "bold", fill: accent, tracking: 0.5pt)[#upper(content)]
  v(3pt)
}

#let section-heading(content) = {
  v(6pt)
  text(size: 10.5pt, weight: "bold", fill: rgb("#333333"))[#content]
  v(2pt)
  line(length: 100%, stroke: 0.5pt + rgb("#dddddd"))
  v(4pt)
}

#let job-header(jobtitle, company, location, dates) = {
  text(size: 9.5pt, weight: "bold", fill: accent)[#jobtitle]
  text(size: 9pt, fill: gray)[ | #company#if location != "" [, #location]]
  if dates != "" {
    text(size: 9pt, fill: gray)[ | #dates]
  }
  v(3pt)
}

// A bullet's label is optional — omit it and the text runs full width.
#let bullet(label, content) = {
  grid(
    columns: (8pt, 1fr),
    gutter: 3pt,
    text(fill: accent, size: 6pt, baseline: 2pt)[●],
    [#if label != "" [#text(weight: "semibold")[#label:] ]#content],
  )
  v(1.5pt)
}

// Render a sidebar list only if it has content, so an omitted key leaves no
// orphaned heading behind.
#let sidebar-section(title, items) = {
  if items.len() > 0 {
    sidebar-heading(title)
    for item in items {
      text(size: 9pt, fill: rgb("#555555"))[#item]
      v(2pt)
    }
    v(6pt)
  }
}

#grid(
  columns: (150pt, 1fr),
  gutter: 16pt,

  // === LEFT SIDEBAR ===
  [
    #text(size: 20pt, weight: "bold")[#identity.at("name", default: "")]
    #v(2pt)
    #text(size: 10pt, fill: gray)[#data.at("title", default: "")]
    #v(10pt)

    #let phone = identity.at("phone", default: "")
    #let email = identity.at("email", default: "")
    #let location = identity.at("location", default: "")
    #if phone != "" or email != "" or location != "" [
      #sidebar-heading[Connect]
      #if phone != "" [#text(size: 9pt)[#phone]
        #v(2pt)]
      #if email != "" [#text(size: 9pt, fill: accent)[#email]
        #v(2pt)]
      #if location != "" [#text(size: 9pt)[#location]
        #v(2pt)]
      #v(6pt)
    ]

    #let skills = data.at("skills", default: "")
    #if skills != "" [
      #sidebar-heading[Skills]
      #text(size: 8.5pt, fill: rgb("#555555"))[#skills]
      #v(8pt)
    ]

    #sidebar-section("Emphasis On", data.at("emphasis", default: ()))
    #sidebar-section("Current Technologies", data.at("technologies", default: ()))

    #let leadership = data.at("leadership", default: "")
    #if leadership != "" [
      #sidebar-heading[Leadership]
      #text(size: 9pt, fill: rgb("#555555"))[#leadership]
      #v(8pt)
    ]

    #if certifications.len() > 0 [
      #sidebar-heading[Certifications]
      #for cert in certifications [
        #text(size: 8.5pt, weight: "semibold")[#cert.at("name", default: "")]
        #let cert-dates = cert.at("dates", default: "")
        #if cert-dates != "" [
          #v(0pt)
          #text(size: 8pt, fill: lightgray)[(#cert-dates)]
        ]
        #v(4pt)
      ]
      #v(4pt)
    ]

    #if education.len() > 0 [
      #sidebar-heading[Education]
      #for ed in education [
        #text(size: 8.5pt, weight: "semibold")[#ed.at("degree", default: "")]
        #v(0pt)
        #let ed-dates = ed.at("dates", default: "")
        #text(size: 8pt, fill: lightgray)[
          #ed.at("school", default: "")#if ed-dates != "" [ (#ed-dates)]
        ]
        #v(4pt)
      ]
    ]
  ],

  // === MAIN CONTENT ===
  [
    #let summary = data.at("summary", default: "")
    #if summary != "" [
      #text(size: 9.5pt, fill: rgb("#555555"))[#summary]
    ]

    #if jobs.len() > 0 [
      #section-heading[Experience]
      #for job in jobs [
        #job-header(
          job.at("title", default: ""),
          job.at("company", default: ""),
          job.at("location", default: ""),
          job.at("dates", default: ""),
        )
        #for b in job.at("bullets", default: ()) [
          #bullet(b.at("label", default: ""), b.at("text", default: ""))
        ]
        #v(4pt)
      ]
    ]
  ],
)
