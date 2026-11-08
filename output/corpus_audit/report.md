# Audit of the Stud PDF corpus

Scope: only the seven PDFs whose filenames start with `Stud` in `data/RAG_text_corpus`. This audits the files on disk, not the database index.

| PDF | Pages | Card occurrences | Source groups within PDF |
|---|---:|---:|---:|
| Stud_Climate_A.pdf | 139 | 158 | 20 |
| Stud_Climate_B.pdf | 124 | 111 | 23 |
| Stud_Forest_Ecology.pdf | 201 | 274 | 16 |
| Stud_Forest_Growth.pdf | 461 | 294 | 20 |
| Stud_Forest_Operations.pdf | 200 | 169 | 20 |
| Stud_Forest_Policy.pdf | 380 | 314 | 19 |
| Stud_Silviculture.pdf | 169 | 219 | 20 |
| **Total** | **1,674** | **1,539** | **138** |

## Counting method

Count one card per substantive entity-list section. The different compilations use Entity List, Entities, Entity, and Entitys, sometimes numbered or bulleted. Counts were cross-checked against card headings and relationship sections. Tables of contents, chapter summaries, and AI-use declarations are excluded. The repeated Relationship Triplets heading on Silviculture PDF page 158 counts only once. Some cards have no literal Knowledge Card heading, so a literal phrase count is insufficient.

These are card occurrences, not deduplicated unique cards, and they are not retrieval chunks. Forest Growth contains repeated material, notably around PDF pages 262–294. A unique-card total requires a separate deduplication policy and audit.

## Meaning of source counts

Seven source PDFs contain 138 within-PDF source groups under the reconciliation choices recorded here. This is NOT a count of 138 unique publications. The same works appear in multiple compilations. Repeated chapters/citations of the same work are grouped within each PDF, and lecture slide sets are generally grouped by course. Distinct courses and explicitly different editions remain separate. Source titles below are abbreviated inventory labels, not corrected bibliographic references.

The Operations count provisionally combines the Wöhrle / Waldverbandaktuell references despite inconsistent years (2015/2025) and different subjects. It also treats the journal-only International Journal of Forest Engineering citation as one unresolved group; its number of underlying articles cannot be determined from the compilation. Consequently a defensible exact number of unique underlying works cannot yet be reported.

## Publication wording

> The student-prepared knowledge corpus comprised seven thematic PDF compilations containing 1,539 knowledge-card occurrences. The cards drew on textbooks, scientific articles, lecture materials, technical guidelines, reports, and web resources. Tables of contents and chapter summaries were excluded from the card count; duplicate card occurrences were retained. A source inventory recorded 138 within-compilation source groups, with repeated works across compilations and unresolved citations retained as such.

## Bibliographic issues to resolve

- Incomplete references: journal names or generic document titles without identifiable articles, authors, years, or identifiers.
- Conflicting metadata: Integrative Forest Management and Silviculture is cited with different years (2023/2026) in Growth and Silviculture; the Climate A compilation prints 2029 for Klimawandel und Vegetation.
- Lecture notes need course, institution, lecturer, year, and version where available.
- The final Silviculture textbook is identified only by an Archive.org item link in the compilation.
- Bibliographic accuracy and publication existence were not independently checked against external catalogues.

## Reproducibility

Run `python output/corpus_audit/audit.py` from the repository root. `summary.json` records input SHA-256 hashes; `card_locations.csv` lists the PDF page of every counted entity section; `source_inventory.csv` and `source_groups.json` record the reconciled source labels. No corpus files, database rows, or embeddings are modified.

## Stud_Climate_A.pdf

1. Atmospheric pollution and climate change — lecture notes
2. Grundlagen der Ökologie II — lecture notes
3. Forstpathologie — lecture notes
4. Campbell Biologie
5. Schadholzaufarbeitung — Fäll- und Schneidetechniken
6. Klimawandel in Deutschland
7. Forstbotanik — lecture notes
8. Waldklimatologie — lecture notes
9. Renaturierung von Waldböden
10. Einführung in den Forstschutz — lecture notes
11. Störungsökologie
12. Biodiversität und Klimawandel
13. Dendrochronologie — lecture notes
14. Meteorologie für Pflanzenwissenschaften — lecture notes
15. Waldökologie — lecture notes
16. Waldökologie: Einführung für Mitteleuropa
17. Wald im Klimawandel: Grundlagen für Adaptationsstrategien
18. Managing Forest Ecosystems: The Challenge of Climate Change
19. Klimawandel und Vegetation — date printed as 2029; requires correction/verification
20. Waldbodenkunde — lecture notes

## Stud_Climate_B.pdf

1. Könz et al.: Ausbreitung von Schadorganismen im Wald unter Einfluss des Klimawandels
2. Temperli and Bugmann: Borkenkäferdynamik im Klimawandel: die Bedeutung der Landschaftsebene
3. Engesser et al.: Forstliche Schadorganismen im Zeichen des Klimawandels
4. Miedaner: Anthropogene Ausbreitung von Pflanzen, ihren Pathogenen und Parasiten
5. Schebeck: Grundlagen der Ökologie II — lecture slides
6. Sanden: Waldökologie: Klimaänderung — lecture slides
7. Niedermair and Hirschberger: Klimawandel & Artenvielfalt
8. Bayerische Staatsregierung: Wald in Gefahr
9. Nordwestdeutsche Forstliche Versuchsanstalt, Band 13: Pilotstudie zu den lokalen Auswirkungen des Klimawandels auf die Forstwirtschaft in ausgewählten Regionen Sachsen-Anhalts
10. Hasenauer: Waldbau 2 — lecture notes
11. Wagner et al.: Mechanisms and Deployment of Resistance in Trees to Insects
12. Implications for the distributional range of the European bark beetles under future climate change
13. Features predisposing forest to bark beetle outbreaks and their dynamics during drought
14. FAO: Climate change impacts on forest health
15. Potential impacts of plant pests and diseases on trees and forests in the United Kingdom
16. Paine: Invasive Forest Insects, Introduced Forest Trees, and Altered Ecosystems
17. Elling et al.: Schädigung von Waldökosystemen
18. Wohlgemuth et al.: Störungsökologie
19. Baier et al.: Der Buchdrucker: Biologie, Ökologie, Management
20. BMEL: Waldstrategie 2050
21. Dirnböck et al.: Integration von Natur- und Klimaschutz im österreichischen Buchenwald — ManageBeech
22. Krott: Regierung des Waldes — as cited; bibliographic identity not independently verified
23. Roux et al.: The forestry & wood sector and climate change mitigation

## Stud_Forest_Ecology.pdf

1. Schume: Waldklimatologie — lecture slides
2. Klimo and Hager: The Floodplain Forests in Europe
3. Heiligmann et al.: Die Pflanze. Biologie für Gymnasien. Band 2
4. Griesberger: Wildökologie in der Forst- und Jagdwirtschaft — lecture materials
5. Newton: Forest ecology and conservation: A handbook of techniques — Forest as habitat
6. Landsberg and Sands: Physiological Ecology of Forest Production — Stand Structure and Dynamics
7. Waldökologie, Sommersemester 2025 — lecture materials; institution given as Universität Wien
8. Kirisits: Forstpathologie — lecture slides
9. Netherer and Stauffer: Forstentomologie — lecture slides/notes
10. Jäger: Waldbau für Jäger
11. Bartsch et al.: Waldökologie: Einführung für Mitteleuropa
12. Chapin et al.: Principles of Terrestrial Ecosystem Ecology
13. Grundlagen der Ökologie 2 — BOKU lecture materials
14. Pfadenhauer and Klötzli: Vegetation der Erde
15. Landmann: Die Natur der Alpen
16. Frei et al.: Quellfluren und Quellbäche. Sprudelnde Schätze im Wald

## Stud_Forest_Growth.pdf

1. Pretzsch: Grundlagen der Waldwachstumsforschung
2. Kramer and Akça: Leitfaden zur Waldmesslehre
3. Grabner: Dendrochronologie — lecture slides
4. Integrative Forest Management and Silviculture — cited here with publication year 2026
5. Landsberg and Sands: Physiological Ecology of Forest Production
6. Lexer et al.: The Sensitivity of the Austrian Forests to Scenarios of Climatic Change
7. Forstliche Ertragslehre — BOKU lecture slides
8. Zustandserhebung und Ertragsprognosen — BOKU lecture materials; slide sets grouped as one course
9. Reininger: Zielstärken-Nutzung oder die Plenterung des Altersklassenwaldes
10. Gilge et al.: Waldwirtschaft heute — 2020 edition
11. Bartsch et al.: Waldökologie: Einführung für Mitteleuropa
12. Allgemeine Botanik — BOKU cooperative course notes
13. Gratzer: Grundlagen der Ökologie II — lecture materials
14. Gadow: Waldstruktur und Wachstum
15. Nothdurft: Forstliche Biometrie II — lecture slides
16. Wildschadensbericht 2024 — attributed to Hangler/ministry
17. Lorenz: Lehrbuch der Forstwirtschaft
18. Forst Holz Papier Österreich: Vermessung des Biorohstoffes Holz — lecture materials
19. Lockow: Waldbestandsmessung – Stichprobenverfahren – Wachstumsmodellierung
20. Biometrie 1 — BOKU lecture materials

## Stud_Forest_Operations.pdf

1. FHP: Harvester und Forwarder in der Holzernte
2. Slovik: Lehrskript für den 2. Jahrgang Forst- & Arbeitstechnik
3. FHP: Holzernte im Seilgelände — Organisation
4. Kaulen et al.: Anforderungsanalyse robotergestütztes Holzernteverfahren — CALAHARI
5. Stampfer: Helicopter Logging
6. Baltic ForBio: Cost-efficient and sustainable forest harvesting methods
7. FHP: Holzernte im Schleppergelände — Methodische Arbeit 4
8. FHP: Holzernte im Seilgelände — Methodische Arbeit 4
9. FHP: Holzernte im Seilgelände — Planung 2
10. Bont et al.: Assessing timber-harvesting systems and forest road networks in Switzerland: new tools
11. Heinimann (1987), Schweizerische Zeitschrift für Forstwesen 138(2):93–117 — title omitted
12. Haberl: Holznutzung mit Mastseilgeräten im Schlitzverfahren
13. Gilge et al.: Waldwirtschaft heute — 2017 edition
14. Stampfer: forestry operations lecture slides, WS 2024 — course title omitted
15. Forst&Technik / forst-praxis (2017) — article title omitted
16. Wassermann: Construction and promotion of forest roads
17. Wöhrle / Waldverbandaktuell — years 2015 and 2025, accident prevention and drones; provisionally one citation group, distinct articles unresolved
18. Stampfer, Spinelli and Visser: Forest Operations — incomplete reference
19. FAO: Forest Operations and Engineering Guidelines — incomplete reference
20. International Journal of Forest Engineering — journal name only, individual articles unresolved

## Stud_Forest_Policy.pdf

1. Pülzl: Die Politik des Waldes
2. Ammer et al.: Der Wald-Wild-Konflikt
3. Hogl: Einführung in die Waldpolitik — 2018–2022 course notes
4. Linser: Indikatoren für nachhaltige Waldbewirtschaftung des Österreichischen Walddialoges
5. Ennöckl: Grundlagen des Rechts — Forst-, Naturschutz-, Klimaschutzrecht slides
6. Hogl: Einführung in die Forstwirtschaft — Vertiefung Waldpolitik, 2023
7. Hofmann: Globale Waldpolitik in Deutschland
8. Nemestothy: Ressourceneffizienz vs. Kaskadenzwang
9. UNECE and FAO: European Forest Sector Outlook Study
10. Husch: Guidelines for forest policy formulation
11. Tuomasjukka: Forest Policy and Economics in Support of Good Governance
12. Brawenz / Lebersorger: Besonderes Verwaltungsrecht für Forstwirte und ausgewählte Rechtsbereiche
13. Löffler: Kleinwaldbewirtschaftung — Beratung, Betriebsplanung und Holzvermarktung
14. Rechkemmer and Schmidt: Neue globale Umweltpolitik
15. Steinsiek: Forst- und Holzforschung im Dritten Reich
16. Ortner: Erfolgsfaktoren für die Beteiligung forstlicher Akteure an der integrierten ländlichen Entwicklung
17. Schwarzbauer / Braun: Holzmarktlehre — course notes
18. Hogl and Pregernig: Grundlagen der Politik — course notes
19. Weinfurter: Waren- und Zahlungsverkehr mit Holzprodukten I — course notes

## Stud_Silviculture.pdf

1. Stadt Wien: Umweltverträgliche Waldbewirtschaftung — Waldbau und Forsttechnik
2. Varga et al.: Guideline for Ecosystem-Based Forest Management in Landscape Conservation Buffer Subzones of World Heritage Beech Forests
3. Grulich et al.: Waldwirtschaft heute — cited as 2020
4. Stimm et al.: Silviculture in the Tropics
5. Waldbau I: Durchforstung, Astung, Düngung — lecture slides
6. Waldbau I: Gefahren der Waldverjüngung — lecture slides
7. Die Folgen der Streuentnahme aus dem Walde — incomplete reference
8. Kulturlandschaft: Äcker, Wiesen, Wälder und ihre Produkte — incomplete reference
9. ForstBW: Richtlinie landesweiter Waldentwicklungstypen
10. waldwissen.net: Waldbau mit Lärche
11. ETH Zürich: Waldbau III — course script waldbau3-03
12. Naturnaher Waldbau — Luxembourg publication
13. Brandenburg: Nachhaltige Waldbewirtschaftung — Realität oder visionärer Anspruch?
14. StarTree D2.1: State of the art, review of silviculture, models and decision support tools for multipurpose trees and non-wood forest products
15. Owari et al.: Integrative Forest Management and Silviculture — cited here as 2023
16. Tognetti et al.: Climate-Smart Forestry in Mountain Regions
17. ETH Zürich: Waldbau I — course script waldbau1-03
18. Bayerische Staatsforsten: Waldbau / Waldumbau web materials
19. The Silviculture of Trees Used in British Forestry — second edition
20. Archive.org item cu31924073869541 — linked textbook, title/author not supplied in the compilation
