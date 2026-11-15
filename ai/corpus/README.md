# RAG corpus source list

PDFs are git-ignored under `ai/`, so this directory records which documents belong in the
corpus. [`sources.csv`](sources.csv) has one row per PDF. The files themselves live in the
local, git-ignored `ai/docs/` directory and are shared outside Git.

The list currently holds the papers added in November 2026. Documents that were already in
the team's batch before then are not listed yet.

## Columns

| Column | Meaning |
| --- | --- |
| `filename` | File name under `ai/docs/`. Shown to users as the citation. |
| `title`, `first_author`, `journal`, `year` | Bibliographic details from Europe PMC. |
| `doi_url` | Link to the published article. |
| `pmcid` | PubMed Central ID. |
| `licence` | Licence code from the PMC open-data record. |
| `topic` | Coverage area, used to spot gaps. |
| `pages` | Page count of the downloaded PDF. |
| `added_by`, `date_added` | GitHub handle and date. |

## Selection rules

- **Open access with a stated licence.** Every current row is CC BY, confirmed in the PMC
  open-data record for that article. Ask the AI codeowner before adding anything with a
  non-commercial, no-derivatives, or unclear licence.
- **Text-based PDFs only.** Ingestion uses `PyPDFLoader`, which does not run OCR. Scanned
  documents produce empty chunks.
- **Educational scope.** Prefer guidelines, reviews, and meta-analyses over single trials and
  molecular-biology papers. The pipeline gives general health education, not clinical advice.
- **Not retracted.** Check the article page before adding it.
- **Stable, descriptive filenames.** Use `short-topic-description-year.pdf`. The filename is
  the citation users see and is part of each chunk ID, so renaming a file re-embeds it.

## Getting the PDFs

The papers were found with the Europe PMC search API and downloaded from the PMC Open Access
dataset on AWS, which allows automated access:

```text
https://pmc-oa-opendata.s3.amazonaws.com/<pmcid>.<version>/<pmcid>.<version>.pdf
```

For example, `PMC7021657` version 1 is at
`https://pmc-oa-opendata.s3.amazonaws.com/PMC7021657.1/PMC7021657.1.pdf`. Save each file under
`ai/docs/` with the name in the `filename` column.

## Adding a paper

1. Check it against the selection rules.
2. Save the PDF in `ai/docs/` and add a row to `sources.csv`.
3. Run `python ai/ingestion_pipeline.py --dry-run` and check the chunk counts.
4. Open a pull request with the `sources.csv` change. The AI codeowner decides when the
   shared collection is re-ingested.

Ingestion deletes stored chunks that are not in the local `ai/docs/` unless `--no-prune` is
passed. Do not run it against the shared collection with a partial copy of the corpus.
