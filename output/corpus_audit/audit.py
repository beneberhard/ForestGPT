"""Read-only audit: count card entity sections in Stud*.pdf; inventory source groups.
Run from the repository root with a Python environment containing pypdf.
Source groups are manually reconciled from the PDF text, not verified bibliography records.
"""
import csv
import hashlib
import json
import re
from pathlib import Path
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
ENTITY = re.compile(r'^\s*(?:[•–-]\s*)?(?:(?:Step\s*)?\d+[.:)]?\s*)?(?:Entity\b|Entities\b|Entitys\b)', re.I)
groups = json.loads((OUT / 'source_groups.json').read_text())
summary = []
card_rows = []
for path in sorted((ROOT / 'data/RAG_text_corpus').glob('Stud*.pdf')):
    reader = PdfReader(path)
    count = 0
    for page_no, page in enumerate(reader.pages, 1):
        lines = (page.extract_text() or '').splitlines()
        for i, line in enumerate(lines):
            if ENTITY.match(line) and not re.search(r'\.{3}', line):
                count += 1
                card_rows.append([path.name, count, page_no, line.strip()])
    summary.append(dict(pdf=path.name, pages=len(reader.pages), card_occurrences=count,
                        source_groups=len(groups[path.stem]),
                        sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
with (OUT / 'card_locations.csv').open('w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['pdf', 'card_ordinal', 'pdf_page_of_entity_section', 'entity_section_marker'])
    writer.writerows(card_rows)
with (OUT / 'source_inventory.csv').open('w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['pdf', 'source_group', 'source_label_as_reconciled_from_compilation'])
    for pdf, entries in groups.items():
        writer.writerows([pdf+'.pdf', i, title] for i, title in enumerate(entries, 1))
(OUT / 'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
report = ['# Audit of the Stud PDF corpus', '',
          'Scope: only the seven PDFs whose filenames start with `Stud` in `data/RAG_text_corpus`. This audits the files on disk, not the database index.', '',
          '| PDF | Pages | Card occurrences | Source groups within PDF |',
          '|---|---:|---:|---:|']
for row in summary:
    report.append(f"| {row['pdf']} | {row['pages']} | {row['card_occurrences']} | {row['source_groups']} |")
report += [f"| **Total** | **{sum(r['pages'] for r in summary):,}** | **{sum(r['card_occurrences'] for r in summary):,}** | **{sum(r['source_groups'] for r in summary)}** |", '',
           '## Counting method', '',
           'Count one card per substantive entity-list section. The different compilations use Entity List, Entities, Entity, and Entitys, sometimes numbered or bulleted. Counts were cross-checked against card headings and relationship sections. Tables of contents, chapter summaries, and AI-use declarations are excluded. The repeated Relationship Triplets heading on Silviculture PDF page 158 counts only once. Some cards have no literal Knowledge Card heading, so a literal phrase count is insufficient.', '',
           'These are card occurrences, not deduplicated unique cards, and they are not retrieval chunks. Forest Growth contains repeated material, notably around PDF pages 262–294. A unique-card total requires a separate deduplication policy and audit.', '',
           '## Meaning of source counts', '',
           'Seven source PDFs contain 138 within-PDF source groups under the reconciliation choices recorded here. This is NOT a count of 138 unique publications. The same works appear in multiple compilations. Repeated chapters/citations of the same work are grouped within each PDF, and lecture slide sets are generally grouped by course. Distinct courses and explicitly different editions remain separate. Source titles below are abbreviated inventory labels, not corrected bibliographic references.', '',
           'The Operations count provisionally combines the Wöhrle / Waldverbandaktuell references despite inconsistent years (2015/2025) and different subjects. It also treats the journal-only International Journal of Forest Engineering citation as one unresolved group; its number of underlying articles cannot be determined from the compilation. Consequently a defensible exact number of unique underlying works cannot yet be reported.', '',
           '## Publication wording', '',
           '> The student-prepared knowledge corpus comprised seven thematic PDF compilations containing 1,539 knowledge-card occurrences. The cards drew on textbooks, scientific articles, lecture materials, technical guidelines, reports, and web resources. Tables of contents and chapter summaries were excluded from the card count; duplicate card occurrences were retained. A source inventory recorded 138 within-compilation source groups, with repeated works across compilations and unresolved citations retained as such.', '',
           '## Bibliographic issues to resolve', '',
           '- Incomplete references: journal names or generic document titles without identifiable articles, authors, years, or identifiers.',
           '- Conflicting metadata: Integrative Forest Management and Silviculture is cited with different years (2023/2026) in Growth and Silviculture; the Climate A compilation prints 2029 for Klimawandel und Vegetation.',
           '- Lecture notes need course, institution, lecturer, year, and version where available.',
           '- The final Silviculture textbook is identified only by an Archive.org item link in the compilation.',
           '- Bibliographic accuracy and publication existence were not independently checked against external catalogues.', '',
           '## Reproducibility', '',
           'Run `python output/corpus_audit/audit.py` from the repository root. `summary.json` records input SHA-256 hashes; `card_locations.csv` lists the PDF page of every counted entity section; `source_inventory.csv` and `source_groups.json` record the reconciled source labels. No corpus files, database rows, or embeddings are modified.', '']
for pdf, entries in groups.items():
    report += ['## '+pdf+'.pdf', '']
    report += [f'{i}. {title}' for i, title in enumerate(entries, 1)]
    report += ['']
(OUT / 'report.md').write_text('\n'.join(report))
print(json.dumps(summary, indent=2))
print('TOTAL CARDS:',sum(r['card_occurrences'] for r in summary))
print('SOURCE GROUPS:',sum(r['source_groups'] for r in summary))
