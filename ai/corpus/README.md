# RAG corpus source list

PDFs are git-ignored under `ai/`, so this directory tracks source metadata without committing
the documents. [`sources.csv`](sources.csv) retains the previously catalogued sources and adds
the newly supplied PDFs found in `ai/docs/`. It is not yet a complete inventory of the earlier
team corpus. The PDF files remain local and are shared outside Git.

The new rows record the contributor(s) supplied for each PDF. Where Karim and Danyil both
listed the same file, it appears once and credits both. The existing catalog entries have not
been removed or replaced.

## Columns

| Column | Meaning |
| --- | --- |
| `filename` | File name under `ai/docs/`. Shown to users as the citation. |
| `title`, `first_author`, `journal`, `year` | Bibliographic details from the source record or PDF where available. |
| `doi_url` | Link to the published article. |
| `pmcid` | PubMed Central ID. |
| `licence` | Licence shown in the source record or PDF; `Unverified` means it still needs checking. |
| `topic` | Coverage area, used to spot gaps. |
| `pages` | Page count of the downloaded PDF. |
| `added_by`, `date_added` | GitHub handle and date. |

## Selection rules

- **Check reuse rights before ingestion or redistribution.** Do not assume a PDF is reusable
  because it is available online. Verify the exact licence and version from the publisher or
  repository record. `Unverified` entries need review; ask the AI codeowner before using a
  non-commercial, no-derivatives, or unclear-licence document.
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
2. Save the PDF in `ai/docs/`, check that it is not already represented by filename or DOI,
   then add one row to `sources.csv` with the contributor credit and verified source metadata.
3. Run `python ai/ingestion_pipeline.py --dry-run` and check the chunk counts.
4. Open a pull request with the `sources.csv` change. The AI codeowner decides when the
   shared collection is re-ingested.

Ingestion deletes stored chunks that are not in the local `ai/docs/` unless `--no-prune` is
passed. Do not run it against the shared collection with a partial copy of the corpus.
