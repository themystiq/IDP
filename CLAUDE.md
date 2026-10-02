# CLAUDE.md

This file documents the Mystiq Labs IDP & GL Reconciliation demo for Claude Code (and any
future contributor). **This is a living document — update it whenever the architecture,
tech stack, or security posture changes.**

## What this is

A Streamlit demo for a CPA firm showing Intelligent Document Processing (IDP): upload one or
more documents (PDF/PNG/JPG) at once, and for each one the vision LLM both detects which of
four supported IRS forms it is — 1099-NEC, 1099-MISC, W-2, or Schedule K-1 — and extracts its
structured data in one call, no manual document-type selection required. Each result is
reconciled against an in-memory ledger (General Ledger for 1099-NEC, 1099-MISC ledger,
payroll ledger for W-2, K-1 ledger for Schedule K-1). The same call also recognizes four
*informational* document types — Bank Statement, Credit Card Statement, Payroll Summary, EIN
Letter, Balance Sheet — which have no ledger to reconcile against, so they're classified and
their headline fields
displayed, but never audited (see "Informational document types" below). The whole batch is
shown as three summary KPI tiles plus taxpayer-ID-grouped customer cards (a customer with both
a W-2 and a 1099-NEC under the same SSN shows as one card with both documents listed) plus,
when present, a separate list of informational documents. The UI runs a custom dark
"executive" theme injected as CSS over Streamlit's own dark base theme.

## Tech stack

| Layer | Choice | Notes |
|---|---|---|
| UI | Streamlit | wide layout, sidebar + two-column main body |
| PDF/image rendering | PyMuPDF (`fitz`) | renders PDF pages to raster images at 200 DPI |
| Image handling | Pillow | in-memory PNG re-encoding, base64 |
| LLM gateway | LiteLLM | provider-agnostic call into `litellm.completion(...)` |
| Vision model | Claude Sonnet 5 (`anthropic/claude-sonnet-5`) | model id overridable via `CLAUDE_MODEL` env var; must include the `anthropic/` provider prefix for LiteLLM routing |
| Schema validation | Pydantic v2 | `Form1099NEC`, `Form1099Misc`, `FormW2`, `FormK1` (reconciled) plus `BankStatement`, `CreditCardStatement`, `PayrollSummary`, `EINLetter`, `BalanceSheet` (informational-only) — per-type extraction contracts, all fields optional except `document_type` |
| Reconciliation | Pandas | in-memory DataFrame match/variance logic |
| Config | python-dotenv | loads `.env`, never hardcoded |
| Theme | `.streamlit/config.toml` (`base = "dark"`) + custom CSS | dark palette set at both the Streamlit-theme level and via injected CSS — see `src/ui/theme.py` |
| Notifications | `slack_sdk` (`WebClient.chat_postMessage`) | optional, best-effort per-document Slack post — see `src/slack_notifier.py` and the security note below |
| Email | `smtplib`/`ssl`/`email` (stdlib) | optional, best-effort real send for Document Chaser's "Approve & Send" — see `src/email_sender.py`; generic SMTP, provider-agnostic |

## Architecture

```
app.py                     # Streamlit entry point — wires panels together, no business logic
src/
  config.py                # env/config loading (API key, model, timeout, size limits)
  exceptions.py             # IDPBaseError hierarchy, caught at the UI boundary
  schemas.py                 # Form1099NEC, Form1099Misc, FormW2, FormK1 (reconciled) + BankStatement, CreditCardStatement, PayrollSummary, EINLetter, BalanceSheet (informational) Pydantic models
  document_processor.py      # PyMuPDF page-to-image rendering + base64 encoding
  extraction.py               # LiteLLM + Claude vision: one call classifies doc type AND extracts fields, timeout
  reconciliation.py            # Pandas engines: reconcile_1099_nec, reconcile_1099_misc, reconcile_w2, reconcile_k1
  ledger_data.py                # in-memory sample General Ledger + 1099-MISC ledger + payroll ledger + K-1 ledger DataFrames
  sample_documents.py            # fills the real IRS templates in documents/ with sample client data (see below)
  slack_notifier.py               # optional, best-effort per-document Slack post of doc name/type/audit status
  ui/
    theme.py                       # dark "executive" CSS injected once from app.py
    sidebar.py                    # branding, engine status, compliance notice, sample loader
    upload_panel.py                 # multi-file upload, size guardrail, per-file preview, extract button
    results_panel.py                 # per-doc extract+reconcile loop, summary KPI tiles, workflow indicator, taxpayer-grouped detail, export
```

Adding a new form type means touching: a schema in `schemas.py`; a field block appended to
`UNIFIED_EXTRACTION_PROMPT` plus a `SCHEMA_BY_DOC_TYPE` (and, if the model might phrase the
type differently than the app's dispatch key, `_DOC_TYPE_ALIASES`) entry in `extraction.py`;
a `reconcile_<type>` function + ledger in `reconciliation.py`/`ledger_data.py`; and a
`RECONCILERS` entry in `results_panel.py` — which now needs four sub-keys per type: `reconcile`,
`ledger`, `subject` (the name to display/group by), `payer` (the issuing entity, shown in the
"Form Type (Payer)" column), `tin` (the taxpayer-ID field used for customer grouping), and
`box_label` (short label for the detail table's "Box" column). There is no UI selector to
update — the model has to be able to tell the new type apart from the existing ones based on
the image alone. Schedule K-1 (`FormK1`) is the reference example for all of this.

**Adding a new *informational* type** (one with no ledger to reconcile against — the current
five are Bank Statement, Credit Card Statement, Payroll Summary, EIN Letter, Balance Sheet) is a smaller version of
the above: a schema in `schemas.py` (field names prefixed per-type, e.g. `bank_statement_*`,
to avoid flat-JSON collisions across types — see the module docstring there), a field block
in `UNIFIED_EXTRACTION_PROMPT` plus `SCHEMA_BY_DOC_TYPE`/`INFORMATIONAL_DOC_TYPES`/
`_DOC_TYPE_ALIASES` entries in `extraction.py`, and an `INFO_FIELDS` entry in
`results_panel.py` (`subject` + a `fields` list of `(label, attr)` pairs — no `reconcile`/
`ledger`/`tin`/`payer` keys, since `RECONCILERS` is specifically the dispatch table for
*audited* types; `results_panel.py` checks `doc_type not in RECONCILERS` to treat a type as
informational rather than maintaining a second parallel "is this reconciled" list). No
`reconcile_<type>` function or ledger needed. Bank Statement (`BankStatement`) is the
reference example.

Design principles:
- **Thin `app.py`.** All logic lives in `src/`; `app.py` only composes the three UI panels.
- **One exception hierarchy.** Every pipeline error subclasses `IDPBaseError` so UI code can
  catch broadly and still show specific messages via `st.error`.
- **Reconciliation status is three-way: GREEN / AMBER / RED, not a binary match/mismatch.**
  Each `reconcile_*` function in `reconciliation.py` separates its findings into
  `monetary_flags` (a missing or mismatched box amount — plain strings) and
  `metadata_mismatches` (TIN/EIN or tax-year mismatch — structured dicts, see below), then sets
  `status = "RED" if monetary_flags else "AMBER" if metadata_mismatches else "GREEN"`. A CPA
  audit tool should still flag a TIN/year mismatch even when the dollar amount ties out (that's
  the AMBER case — a "Compliance Notice," not a false "clean match") — but it shouldn't read as
  loudly as a real dollar variance (RED), which is the whole reason AMBER exists as its own tier
  rather than folding straight into RED. See the docstring in `reconciliation.py` if this needs
  to change.
- **Metadata mismatches are structured data, not pre-formatted strings — the UI renders the
  exact "Extracted (...) vs Ledger (...)" values itself.** Each entry in `metadata_mismatches`
  is `{"field", "label", "extracted", "ledger", "severity", "mask"}` (built by
  `_metadata_mismatch()` in `reconciliation.py`). `results_panel.py`'s `_mismatch_callout()`
  renders each one as `[doc_type] {label} mismatch: Extracted ({extracted}) vs Ledger
  ({ledger})`, masking `extracted`/`ledger` through the existing `_mask_tin()` when `mask` is
  True (TIN/EIN fields) — never for `tax_year`, which displays as plain years. `severity`
  picks `st.error`/🛑 vs `st.warning`/⚠️, but every current metadata mismatch (TIN/EIN and tax
  year alike) uses `"warning"` — amber, matching the AMBER reconciliation status these checks
  produce (see above). TIN/EIN mismatches were briefly rendered as `st.error`/🛑 (red), but
  that read as more severe than a real dollar variance despite the status itself being AMBER,
  not RED — a real inconsistency, not a stylistic choice, so it was corrected back to amber.
  `"error"` severity remains available in `_metadata_mismatch()` for a genuinely more serious
  future check, but nothing currently uses it. Rendered directly beneath the monetary-flag
  warnings in the same "Audit Flags:" callout section. `audit_flags` still
  carries a flattened plain-string version of every finding (built from the same
  `_mismatch_flag_text()` helper, so it can't drift from what the UI shows) for CSV/JSON
  export and `_status_cell`'s extraction-failure fallback — the main Customer Reconciliation
  table itself gets no new columns for this; Tax Year/TIN/Payer Name are surfaced only in the
  callouts below the table, not as permanent table columns (deliberately, to keep the table
  focused on monetary alignment).
- **Sample documents are real IRS templates, filled at runtime.** `sample_documents.py` fills
  the actual blank IRS PDFs (`documents/f1099nec.pdf`, `f1099msc.pdf`, `fw2.pdf`,
  `f1065sk1.pdf`) via PyMuPDF's AcroForm widget API, using the same client data as
  `ledger_data.py`. These 4 templates are official public IRS forms (no PII — they're blank),
  so unlike the old synthetic-mockup approach, they *are* checked-in binary assets; the
  original "no binary assets" principle was about avoiding fake PII in git history, which
  doesn't apply here. Each builder fills the recipient/employee "Copy B" page (found by
  searching the template's page text for "Copy B"/"For Recipient", since these templates are
  multi-page with Copy A/1/B/2/instructions all bundled in one file) and extracts just that
  page into a standalone single-page PDF — the extraction pipeline only ever reads page 1 of
  an upload. Field names on these templates are cryptic and auto-generated (e.g. `f2_20[0]`),
  so the field mapping in each builder was derived by correlating widget position with the
  nearby printed box label, not by reading the field name. Neither the W-2 nor K-1 template
  has a fillable tax-year field on its Copy B/main page (the year is preprinted on the form
  itself), so `tax_year` is accepted but silently ignored by those two builders. The 1099-MISC
  and K-1 builders only fill a box when that value is given, mirroring a real form where an
  unused box is left blank — so the vision model has a genuine basis to return `null` rather
  than being nudged to hallucinate a value. `get_sample_catalog()`/`build_sample()` build one
  sample on demand (used by the sidebar loader, cheap enough for every rerun);
  `get_sample_documents()` eagerly builds all of them and is used by the `if __name__ ==
  "__main__":` script at the bottom of the file, which regenerates the `documents/*.pdf`
  sample outputs (run via `python -m src.sample_documents`).
- **Every schema is lenient by design.** All fields except `document_type` are
  `Optional[...] = None` on `Form1099NEC`, `Form1099Misc`, `FormW2`, and `FormK1` alike. Every
  extraction prompt in `extraction.py` tells the model to return `null` for anything illegible
  rather than guess. Every `reconcile_*` function in `reconciliation.py` and the results panel
  branch on `None` explicitly (missing name → no match, missing amount → "could not be
  extracted" flag) instead of relying on Pydantic to reject an incomplete extraction. Keep new
  form types consistent with this — don't reintroduce required fields.
- **`FormK1`'s box amounts are the one exception to "amounts can't be negative."**
  `ordinary_business_income` and `net_rental_real_estate_income` use their own `round_amount`
  validator (no non-negative check) because a partner's K-1 share is legitimately allowed to
  be a loss. Don't reuse the other schemas' `validate_amount` validator for K-1 fields.
- **Ledger "no match" defaults to $0.00, never `None`.** Every `reconcile_*` function routes
  its "no ledger entry found" case through the shared `_no_match_result` helper in
  `reconciliation.py`, which sets `gl_amount = 0.00` and computes `variance` against that
  default whenever an extracted amount exists (rather than leaving both as `None`). This was a
  deliberate fix: `None` values broke currency formatting and produced "N/A" cells even when
  there was a real number to show and compare — a $0.00 ledger default with the "no entry
  found" audit flag still present is more useful and no less honest about the mismatch.
- **1099-MISC reconciles on Box 1 + Box 3 combined**, not per-box. `reconcile_1099_misc` sums
  `rents` and `other_income` (treating a missing box as 0, unless *both* are missing) and
  compares that total to a single ledger `amount` per vendor. The assumption: a GL entry for a
  1099-MISC vendor represents total reportable payments for the year regardless of which box
  they'd land in. Revisit if a vendor can appear on multiple 1099-MISC forms with box amounts
  that shouldn't be summed together.
- **Doc type comes from the model, not the user.** There is no document-type dropdown.
  `extract_and_classify` in `extraction.py` makes a single vision call whose prompt asks the
  model to both identify the form (1099-NEC / 1099-MISC / W-2) and extract its fields in the
  same response, returning `(extracted_object, doc_type)` per document.
- **Batch upload, one row of state per document.** `upload_panel.py`'s `st.file_uploader` has
  `accept_multiple_files=True` and returns a list of `{"name", "images", "base64_images"}`
  dicts (one per valid file — oversized or unrenderable files are skipped with `st.error` and
  never reach this list). `results_panel.py`'s `_process_document` runs extraction +
  reconciliation for exactly one document and **never raises** — any failure is captured in
  that document's own `"error"` key — so one bad file in a batch can't abort the rest. The
  full list of per-document outcomes is stored as `st.session_state["batch_results"]` after
  the Extract button is clicked, and every downstream read (summary metrics, customer-grouped
  detail, CSV/JSON export) iterates that stored list — nothing re-runs extraction or
  re-derives type on a later render.
- **Customer grouping keys on taxpayer ID, not name.** `_group_by_taxpayer` in
  `results_panel.py` groups successfully-processed documents by the normalized digits of
  whichever TIN field applies (`employee_ssn` for W-2, `recipient_tin` for 1099-NEC/MISC,
  `partner_tin` for K-1) — via each `RECONCILERS[doc_type]["tin"]` accessor — not by the
  extracted name string. This is deliberate: a person's W-2 and their LLC's 1099-NEC have
  different name strings (their personal name vs. their business's name) but, if the payer
  used the individual's own SSN on the 1099 instead of the LLC's EIN, the *same* TIN — so
  TIN-matching is the only identifier that can correctly merge multi-document taxpayers
  without fragile name-fuzzing. A document with no extractable TIN gets its own unmerged group
  (keyed by `id(r)`) rather than being silently lumped in with anything else. Display always
  masks the TIN to last-4 (`_mask_tin`) — never shows the raw number in the UI. `_mask_tin`
  detects EIN vs SSN from the *input string's own dash position* (`XX-XXXXXXX` vs
  `XXX-XX-XXXX`), not digit count — both are 9 digits, so counting alone can't tell them
  apart, and doing so once caused every business EIN to render in the personal SSN shape
  (`***-**-1234`) instead of its own (`**-***1234`). Don't go back to a digit-count-only check.
- **Informational document types never reach `_group_by_taxpayer` or the Customer
  Reconciliation cards at all.** A Bank Statement / Credit Card Statement / Payroll Summary /
  EIN Letter / Balance Sheet (see "Adding a new informational type" above) has no
  `RECONCILERS` entry — no `tin`/`subject` accessor to call — so `_group_by_taxpayer`
  explicitly skips any doc whose `doc_type in INFORMATIONAL_DOC_TYPES`, and
  `render_results_panel` renders them instead in their own
  "📋 Other Identified Documents (not reconciled)" list (driven by `INFO_FIELDS`), right below
  the "⚠️ Failed to Process" list and above the Customer Reconciliation section. Their
  `reconciliation` key is `None` on the `_process_document` outcome dict — by design, not an
  error — so every place that reads `r["reconciliation"]` (KPI counts, CSV export, the
  workflow indicator) treats `None` as "not applicable" rather than crashing on it or
  double-counting it as a failure.
- **The customer card badge (`_customer_badge`) shows every nonzero count side by side:**
  `🟢 {green} Match(es)`, `🟡 {amber} Compliance Notice(s)`, `🔴 {red} Variance(s)`, joined with
  `" | "` for a taxpayer with a mix — e.g. someone with one clean W-2 and one discrepant
  1099-NEC shows `🟢 1 Match | 🔴 1 Variance`, not a fraction. The green/red wording came from a
  user-supplied mockup and should be preserved if the layout changes again; amber was added
  later as a third tier for metadata-only (TIN/tax-year) mismatches — see the reconciliation
  status note above.
- **The batch-level summary is three custom HTML KPI cards, not a table (and not `st.metric`
  either).** "TOTAL BATCH INGESTED" (shows `{processed_count} / {total_count}`, i.e.
  successfully-processed vs. total in the batch), "RECONCILED" (GREEN count), "VARIANCES"
  (RED + ERROR count, combined under one number — an extraction failure is folded into "needs
  review" alongside genuine dollar variances, since both require a human to look at the
  document). `st.metric` was tried first but can't render a two-tone value like "3 / 3" or a
  description line under the number, so `_kpi_card` in `results_panel.py` builds raw HTML
  instead, styled by the `.idp-kpi-*` rules in `theme.py`. There used to be a flat
  per-document summary `st.dataframe` here (and later a plain `st.metric` version); both were
  replaced. **Failed documents still need to be visible somewhere** — see the "⚠️ Failed to
  Process" list right below the cards (only rendered when `error_count > 0`), which is what
  keeps `_group_by_taxpayer` skipping errored documents (by design — they have no extracted
  name/TIN to group by) from making those documents invisible.
- **The KPI card accent dot color is the only per-card visual difference** — neutral
  blue-gray (`--idp-accent-neutral`) for the ingested-count card, green for reconciled, and for
  "Action Required," a color that now depends on what's actually in the batch: red
  (`--idp-accent-danger`, via the `.idp-kpi-danger` class) if any document has a real dollar
  variance or failed extraction, amber (`--idp-accent-warning`) if the worst thing present is a
  metadata-only (TIN/tax-year) mismatch, and amber again for the zero-issues "0 Variances"
  resting state. This replaces an earlier, flatter design where "Action Required" was always
  amber regardless of severity — that flat design predates the AMBER reconciliation status
  (see above) existing as a distinct tier from RED, which is the "specific reason" an earlier
  version of this note said would be needed to ever wire `--idp-accent-danger` in.
- **The workflow pipeline indicator (`_render_workflow_indicator` in `results_panel.py`) is a
  state readout, not a progress bar.** It shows Ingested → Extracted → Validated → Reconciled
  as four small dots + thin connecting lines, and every stage's color is derived from real
  data on each render — nothing animates, polls, or advances itself. Specifically:
  - **Ingested** = `bool(documents) or bool(batch_results)` — true as soon as files sit in the
    uploader, even before the Extract button is clicked. This is the only stage that can show
    *before* `batch_results` exists, which is why the function is called before the
    `if not batch_results: return` early-exit, not after.
  - **Extracted and Validated always resolve identically.** `extract_and_classify` performs
    the vision call and Pydantic validation as one atomic step, and a failure there (bad
    call vs. bad shape) is caught by the same `except ExtractionError` in `_process_document`
    — there's no data left over that could tell the two failure modes apart. Rather than
    invent a fake distinction, both stages key off the same real signal: whether at least one
    document in the batch has a non-`None` `extracted` value. If this ever changes (e.g.
    `_process_document` starts preserving *which* sub-step failed), that's the place to
    split them — don't fake it from the results_panel side.
  - **Reconciled** is `"amber"` (not green) when at least one document reconciled with a
    non-`GREEN` status — reusing the same status semantics as the KPI cards and Customer
    Detail badges. It's `"failed"` (red) only when *nothing* in the batch reached
    reconciliation at all (total failure), not merely when some documents have variances.
    A batch made entirely of informational doc types (see above) has zero reconciled
    documents by design, not by failure — so this stage also checks whether anything
    extracted successfully with `reconciliation is None` (an `informational_count`) before
    calling it `"failed"`, and only reds out when neither count is nonzero.
  - **The "next actionable" stage** (hollow dot with a `--idp-accent-info` blue ring, not
    filled) only ever applies to "Extracted," and only in the gap between files being loaded
    and the Extract button being clicked — the one point in this app's workflow where a
    stage is genuinely "done and waiting on a human action" rather than resolving atomically
    with its neighbors. Don't add "next" treatment to Validated/Reconciled; the current
    architecture has no code path where they'd be pending while Extracted is already done.
- **The upload-panel file list shows a `[doc_type]` badge only once a real, confirmed result
  exists for that exact filename** — `upload_panel.py` builds `confirmed_types` by matching
  `doc["name"]` against `st.session_state["batch_results"]`'s `doc_name`/`doc_type` fields.
  It never guesses a type from the filename itself. Two consequences worth knowing:
  - **The sidebar's sample loader gives each sample a name derived from its label**
    (`f"{label}.pdf"` in `sidebar.py`), not a fixed `"sample.pdf"`. With a constant name,
    loading a *different* sample after one had already been processed would incorrectly
    inherit the previous sample's badge on lookup — don't revert this name-uniqueness fix
    while working on the sample loader.
  - **The badge can lag by one interaction.** `app.py` calls `render_upload_panel()` (which
    reads `batch_results` to decide what badge to show) *before* `render_results_panel()`
    (which is what actually runs `_process_document` and writes `batch_results` this pass).
    So on the exact script run where "Extract & Audit" was just clicked, the file list still
    renders with no badge — session_state only reflects the fresh results starting on the
    *next* rerun (expanding a Customer Reconciliation card's own toggle, uploading another file, etc.
    triggers this; merely toggling an `st.expander` open/closed does not — that's pure
    client-side state with no server round-trip, easy to mistake for a "rerun" when testing
    this by hand). This is a structural consequence of the badge list sitting above the
    button that triggers the classification it displays, not a bug — fixing it fully would
    mean splitting `render_upload_panel` so the file list renders *after*
    `render_results_panel` (in a second `with left:` block in `app.py`), which wasn't done
    since the one-interaction lag was judged an acceptable tradeoff for the added complexity.
- **The Customer Reconciliation cards are the only per-document breakdown left.** There's no longer a
  flat per-document table anywhere in the UI (there was one before customer-grouping was
  added, and another briefly as a "Summary" table before the metrics-tile redesign) — both
  were fully superseded. If a future change needs a flat cross-document view again, don't
  resurrect the old dataframe verbatim; check whether the metrics tiles + failed-list +
  customer cards already cover the need first.
- **Export is framed as the workflow's final stage, not a generic utility.** The heading is
  "Export Results" (not "Export") with a one-line caption ("Download the processed and
  audited data") underneath, and the CSV button is `type="primary"` (the same emerald fill as
  the "Extract & Audit Document(s)" button) while JSON stays secondary/outlined — CSV was
  picked as primary since it's the more common CPA/spreadsheet path, not because JSON matters
  less. Getting the primary-green fill onto `st.download_button` (not just `st.button`)
  required extending `theme.py`'s `[kind="primary"]` CSS rule to also match
  `.stDownloadButton > button[kind="primary"]` — the two widgets use different wrapper
  classes, so a rule scoped to only `.stButton` silently misses download buttons. A future
  third export action (e.g. "Export Audit Report") can join as a third `st.columns()` entry
  without restructuring this section — don't add it speculatively, only when that
  functionality actually exists.
- **Slack notifications fire per-document, inside the processing loop — not once per
  batch.** `render_results_panel`'s extract-button handler used to build `batch_results` with
  a single list comprehension (`[_process_document(doc) for doc in documents]`); it's now an
  explicit `for` loop so `_notify_slack_outcome` can run immediately after each document's
  `_process_document` call, before the next document starts. This means a CPA watching the
  Slack channel sees each result as it lands rather than all of them at once after the whole
  batch finishes — meaningful for a large batch under the existing 30s-per-document timeout
  (see the Security section's per-document timeout note). The status label sent
  (`_STATUS_DISPLAY` in `slack_notifier.py`) reuses the same five-way vocabulary as everywhere
  else in the UI: Clean Match / Compliance Notice / Variance / Informational — Not Reconciled
  (for `doc_type in INFORMATIONAL_DOC_TYPES`) / Failed to Process (for a document whose
  `"error"` key is set). Slack failures are collected into
  `st.session_state["slack_errors"]` and surfaced as one `st.warning` summary (count only,
  not per-document) right under the "Processed N document(s) in Xs" caption — not inline per
  document, to avoid interleaving an infrastructure concern with the audit-flag callouts
  later in the page.
- **One call, not two.** Classification and field extraction happen in a single LiteLLM
  request (`UNIFIED_EXTRACTION_PROMPT` lists every field across all three forms and tells the
  model to null out whatever doesn't apply to the type it detects), rather than a cheap
  classify-call followed by a per-type extract-call. This was a deliberate latency/cost
  tradeoff — one API call fits the existing 30s timeout unchanged and costs half as much per
  document. If classification accuracy ever becomes a problem, the two-call split is the
  documented alternative if that's ever needed: classify with a small/cheap call first, then
  run the existing per-type prompt unchanged — not currently implemented.
- **`document_type` string casing is normalized at the dispatch boundary, not in the schema.**
  The model returns `"W2"` (matching `FormW2.document_type`'s own default), but every other
  dispatch key in the app (`RECONCILERS`, `SCHEMA_BY_DOC_TYPE`, the sample dict, the ledgers)
  uses `"W-2"`. Rather than change the schema default, `_normalize_doc_type` in `extraction.py`
  maps `"W2"`/`"W-2"`/`"1099NEC"`/etc. to the canonical dispatch keys before anything looks the
  type up. If a new form type is added, its casing quirks belong in `_DOC_TYPE_ALIASES`, not
  scattered across the UI files.
- **An unrecognized document_type is a user-facing error, not a crash.** If the model returns
  something `_normalize_doc_type` can't map (e.g. someone uploads an invoice or a random PDF),
  `extract_and_classify` raises `ExtractionError` with a message telling the user the file
  doesn't look like a supported form — this is the one new failure mode auto-detection
  introduced that didn't exist when the user picked the type manually.

## Document Chaser

A second, related workflow in its own top-level tab (`app.py`'s `st.tabs(["🧾 IDP & Reconciliation", "📋 Document Chaser"])`)
— previews what will later become a standalone "document chaser agent." Rather than a human
uploading one document at a time, it scans a fixed roster of client folders, extracts and
classifies whatever's in each one, compares that against a per-client checklist of required
documents, and drafts + posts a reminder email to Slack for anything missing or wrong.

```
src/
  chaser_data.py        # CLIENT_CHECKLISTS (client name, folder, [{doc_type, expected_subject}]) + client_folder_path()
  chaser_fixtures.py     # regenerates documents/clients/*/*.pdf — run via `python -m src.chaser_fixtures`
  document_chaser.py      # scan_client_folder, _match_checklist, compose_reminder_email, run_chaser_for_client
  ui/
    chaser_panel.py          # the "Check Documents & Email Clients" button + per-client result cards
documents/clients/<Folder>/   # one real directory per client, checked into git (synthetic demo data, no real PII —
                               # same justification as documents/*.pdf) — Rachel_Green/ is deliberately empty (.gitkeep)
```

Design notes:
- **Reuses the IDP extraction pipeline verbatim — no parallel extraction code.**
  `scan_client_folder` in `document_chaser.py` calls the exact same
  `document_processor.render_upload_to_images` / `image_to_base64_png` →
  `extraction.extract_and_classify` chain that `upload_panel.py`/`results_panel.py` already
  use, just fed from `Path.read_bytes()` instead of an `UploadedFile`. A per-file
  `ExtractionError`/`ExtractionTimeoutError` is caught individually (same resilience pattern
  as `_process_document`), so one bad file can't abort the rest of a client's folder, or the
  rest of the batch.
- **A checklist item can be "missing" or "mismatched" — not just present/absent.** Each
  `CLIENT_CHECKLISTS` entry in `chaser_data.py` pairs a `doc_type` with an
  `expected_subject` (the name that should be on it). `document_chaser._match_checklist`
  looks for an extracted document of that `doc_type`; if none exists, the item is
  `"missing"`. If one exists but its identity field (`_SUBJECT_ATTR[doc_type]` —
  `recipient_name` for 1099-NEC/MISC, `employee_name` for W-2, `partner_name` for K-1)
  doesn't case-insensitively match `expected_subject`, it's `"mismatched"` — the right kind
  of form, filed under the wrong client. This is the whole point of the demo fixture roster
  (see below): a chaser that only checked "does a file exist" couldn't catch this.
  `_SUBJECT_ATTR` intentionally duplicates (in 4 lines) the "subject" lambdas already in
  `results_panel.RECONCILERS`, rather than importing a UI module from this business-logic
  one — don't go reach into `results_panel.py` from here to deduplicate it.
- **The four demo clients are a deliberately-built scenario matrix, not arbitrary sample
  data.** Each reuses an *existing* identity from `sample_documents._SAMPLE_SPECS` (no new
  synthetic client data was invented): **John Doe** (1099-NEC + W-2, both correct — the
  complete case; also the one existing identity that already spans two doc types, since the
  original IDP sample set used him to demo TIN-based grouping), **Jane Smith** (checklist
  asks for K-1 + 1099-NEC, folder only has the K-1 — the partial case), **Sam Whitfield**
  (checklist wants his own W-2, folder actually has **Jordan Ellis's** W-2 — the wrong-client
  case), **Rachel Green** (checklist wants a W-2, folder is empty — the none-received case).
  `chaser_fixtures.py`'s `_FOLDER_CONTENTS` is the single source of truth for which
  `build_sample(doc_type, label)` call fills each folder; re-run
  `python -m src.chaser_fixtures` any time that mapping changes. Each fixture file is named
  by its checklist slot (e.g. `W-2.pdf`), not its true contents — the filename itself gives
  no hint that Sam Whitfield's W-2 is wrong; only extraction reveals it, which is the
  demo's point.
- **The reminder email is drafted, posted to Slack automatically, and only sent for real
  after an explicit human approval.** `document_chaser.compose_reminder_email` returns a
  plain `{"subject", "body"}` dict; `_run_batch` in `chaser_panel.py` always posts that draft
  to Slack (when `slack_enabled()`) as soon as a client's scan finishes, same as before. The
  draft is then also shown in the UI as two editable fields — `st.text_input("Subject", ...)`
  and `st.text_area("Body", ...)`, both key-bound directly to per-client session-state
  entries (`chaser_subject_<folder>` / `chaser_body_<folder>`) — behind two buttons:
  **✏️ Edit** (flips those fields from disabled/read-only to editable; the default on a fresh
  draft is *disabled*, so a reviewer sees the system's own wording first) and
  **✅ Approve & Send** (calls `email_sender.send_email` with whatever is *currently* in
  those two fields — edited or not — then locks both buttons and both fields by setting that
  client's `chaser_sent_<folder>` flag). Re-running "Check Documents & Email Clients" resets
  every client's subject/body/editing/sent state back to a fresh draft — see `_run_batch`.
- **`src/email_sender.py` is the real-send counterpart to `slack_notifier.py`** — same
  best-effort/non-raising shape (`email_enabled()` gate, `send_email(to, subject, body) ->
  (sent, error)`), but plain `smtplib`/`ssl`/`email.message.EmailMessage` from the standard
  library, not a third-party SDK. `config.py`'s `SMTP_HOST`/`SMTP_PORT`/`SMTP_USERNAME`/
  `SMTP_PASSWORD`/`SMTP_FROM_EMAIL` are deliberately generic (not Gmail-specific in name or
  code) so that swapping the demo's Google Workspace account for a production client's own
  mail server is purely a `.env` change — see the user's own framing of this when the
  feature was requested. `SMTP_HOST`/`SMTP_PORT` default to `smtp.gmail.com`/`587`;
  the other three have no default and gate `email_enabled()`.
- **Every "Approve & Send" goes to `config.CHASER_EMAIL_OVERRIDE`, not a real client
  address — a deliberate, temporary demo safety valve**, not a config the demo roster will
  outgrow gracefully. The four `CLIENT_CHECKLISTS` entries in `chaser_data.py` have no email
  field at all (there's no real "John Doe" to accidentally email), so `chaser_panel.py`
  always sends to this one override address regardless of which client's card the click came
  from, and says so explicitly in the panel's own caption. Defaults to
  `ramya.rajaram@mystiqlabs.ai` via `.env`'s `CHASER_EMAIL_OVERRIDE`. Remove this override
  (and give `CLIENT_CHECKLISTS` entries real addresses) before any real client send.
- **The per-client `st.expander` is pinned open via session state for the same reason as the
  Customer Reconciliation cards' JSON toggle** (see that note elsewhere in this file):
  clicking **Edit** or **Approve & Send** triggers a script rerun, and `st.expander` without
  a pinned `expanded=` snaps back to collapsed on that rerun — which would hide the very
  fields/buttons the reviewer just clicked. `chaser_panel.py` tracks this per client as
  `chaser_expanded_<folder>`, set `True` by `_run_batch` for any client with an outstanding
  item (so cards needing review auto-open right after a scan) and `False` for a client with
  nothing outstanding (so a now-resolved client collapses back down on the next scan).
- **`post_chaser_email` is a deliberately wider Slack privacy boundary than
  `notify_document_outcome`, and the two are documented separately in
  `slack_notifier.py`'s module docstring because of it.** The IDP workflow's Slack message
  never includes a name (just filename/type/status); a chaser reminder email *is* a message
  to a named client about named missing documents, so the client's name and the
  missing/mismatched doc types necessarily appear in what gets posted. It still never
  includes a TIN/SSN/EIN or a dollar amount. `slack_notifier.py`'s `_post(text)` helper is
  shared by both functions (factored out of what used to be `notify_document_outcome`'s
  inline `WebClient` call) so the actual Slack API call and its best-effort/non-raising
  contract can't drift between the two message types.
- **The Slack message's "Edit"/"Approve & Send" buttons are link buttons, not Slack
  Interactivity — a deliberate scope decision.** Real Slack Interactivity (a button whose
  click is handled server-side, in-place, without leaving Slack) needs the Slack app's
  Signing Secret, a public HTTPS Request URL, and a webhook receiver to verify and handle
  the callback — a meaningful chunk of new infrastructure. Instead, `post_chaser_email`
  builds a Block Kit `actions` block with two `url`-type buttons (see
  `slack_notifier.post_chaser_email`), each pointing at
  `{config.APP_BASE_URL}/?tab=chaser&client=<folder>` — clicking either just opens that URL
  in a browser; Slack needs nothing special configured for this (`url` buttons aren't
  Slack's interactive-component kind). `chaser_panel.py`'s `render_chaser_panel` reads
  `st.query_params.get("client")` at the top and force-sets that one client's
  `chaser_expanded_<folder>` flag, so the linked card is already open when the page loads.
  **Known limitation:** `st.tabs()` has no API to select the active tab programmatically, so
  the user still has to click the "Document Chaser" tab once themselves after landing — the
  query param only saves hunting for the right card once there. If real one-click
  Interactivity is wanted later, that's the documented harder path, not implemented here.
- **One Slack post per client, fired as that client's scan finishes** — `chaser_panel.py`'s
  `_run_batch` loops over `CLIENT_CHECKLISTS` and calls `post_chaser_email` right after each
  client's `run_chaser_for_client` call, rather than collecting every result first and
  posting once at the end. Same per-item-as-you-go pattern as the IDP workflow's
  `_notify_slack_outcome` loop in `results_panel.py`, for the same reason — a CPA watching
  Slack sees each client's status as it's determined, not all at once after the whole roster
  finishes. A client with nothing outstanding (John Doe, today) gets no Slack message at all.

## Theming

A single dark "executive" theme, set at two levels that need to stay in sync:
- **`.streamlit/config.toml`** (`[theme]` with `base = "dark"` and the palette below) — this
  is what Streamlit's own native widget chrome (selectboxes, sliders, the toggle switch, etc.)
  reads. CSS injection alone can't reach everything a native widget renders internally.
- **`src/ui/theme.py`** (`inject_custom_theme()`, called once from `app.py` right after
  `st.set_page_config`) — CSS targeting Streamlit's `data-testid` attributes for the polish
  the theme config can't do (rounded corners, box-shadows, hover transitions), plus the
  `.idp-kpi-*` classes that style the Batch Summary's custom-HTML KPI cards (see
  `_kpi_card` in `results_panel.py` — not `st.metric`, which was replaced; see below).

Palette (defined as CSS custom properties in `theme.py`, and mirrored as raw hex in
`config.toml` since TOML can't reference CSS variables):

| Token | Hex | Use |
|---|---|---|
| `--idp-bg-primary` | `#0E1117` | page background |
| `--idp-bg-secondary` | `#1E232F` | sidebar, cards, KPI tiles, expanders |
| `--idp-text-primary` | `#FFFFFF` | headers |
| `--idp-text-secondary` | `#A0AEC0` | captions/subtext |
| `--idp-accent-success` | `#10B981` | primary buttons, hover glow, focus rings, "Reconciled" KPI dot |
| `--idp-accent-danger` | `#EF4444` | "Action Required" KPI dot when a real dollar variance is present (`.idp-kpi-danger`) |
| `--idp-accent-warning` | `#F59E0B` | "Action Required" KPI dot for a metadata-only mismatch or the zero-issues state |
| `--idp-accent-neutral` | `#64748B` | "Total Batch Ingested" KPI dot |
| `--idp-accent-info` | `#3B82F6` | workflow pipeline's "next actionable stage" ring |

Design notes:
- **This is a committed dark theme, not a light/dark toggle.** The hex values are fixed, not
  tied to `prefers-color-scheme` or Streamlit's runtime theme switch. If a user manually flips
  Streamlit's built-in theme picker (⋮ menu → Settings) to "light", the injected CSS still
  forces dark backgrounds and the two will visually clash. Acceptable since the goal was one
  consistent look, not a toggle — revisit only if a light mode is explicitly requested later.
- **Native `st.success`/`st.error`/`st.warning` alert colors are deliberately left alone.**
  `theme.py` only adds rounding/spacing to `[data-testid="stAlert"]`. There's no stable,
  version-safe CSS selector for Streamlit's internal success/error/warning fill colors short of
  matching against emoji/SVG internals, which breaks across Streamlit versions. The app's own
  🟢/🔴/⚠️ emoji-based status system (already used throughout `results_panel.py`) carries the
  actual green/red/amber semantics instead. `--idp-accent-warning` and `--idp-accent-danger`
  are both wired in via the Batch Summary KPI cards' `.idp-kpi-warning`/`.idp-kpi-danger`
  classes (see the reconciliation status note above for what decides which one shows).
- **Typography weight hierarchy is deliberately non-default and was tuned against measured
  computed styles, not guessed.** Streamlit's own native weights turned out to be: h1 (main
  page title) `700`, h3 (section headings — "Document Upload", "Extracted Data & Audit",
  "Customer Reconciliation", "Export Results") `600`, `st.expander`
  summaries (file-list entries, Customer Reconciliation card headers, sidebar's "Load Sample
  Document") `400`, plain body text `400`.
  That left card/customer titles visually tied with plain metadata (both `400`) — a collapsed
  middle tier — while section headings at `600`/28px still read as "loud" relative to their
  actual importance. `theme.py` now pins an explicit ladder: h1 stays untouched at native
  `700`; `h3 { font-weight: 550 !important; }`; `[data-testid="stExpander"] summary {
  font-weight: 500 !important; }`; `.idp-privacy-title` (the sidebar's small "Data Privacy"
  card heading, a card-title instance) dropped from `700` to `500` to match. Body text /
  captions were already `400` and untouched. The `!important` on both rules is load-bearing —
  Streamlit assigns weight via higher-specificity emotion-generated classes on the elements
  themselves, so a bare-tag CSS rule without `!important` would silently lose the cascade.
  `h2` (the sidebar's "Mystiq Labs" wordmark) is intentionally left at its native weight —
  it's brand identity, not a section heading, and wasn't part of this hierarchy. Don't touch
  `.idp-kpi-label` / `.idp-pipeline-label` / other small uppercase micro-labels for "hierarchy
  consistency" without a specific reason — they're already small + muted-colored, which reads
  as the metadata tier regardless of their own font-weight value, and were left alone the last
  time this was tuned to avoid scope creep into components the request didn't name.
- **Vertical spacing is selectively targeted, not a blanket gap increase, and every Streamlit
  element shares one generic wrapper class** (`div[data-testid="stElementContainer"]`) — there
  is no per-widget class to hook. The only reliable way to add space after *one specific*
  kind of content is `:has()` on that wrapper, keyed to a stable inner `data-testid`/class:
  `:has([data-testid="stFileUploaderDropzone"])` (space before the file list),
  `:has([data-testid="stExpander"])` (a modest bump — keeps stacked document/customer cards
  themselves compact), `:has(> div.stButton), :has(> div.stDownloadButton)` (space before an
  action button). `h3 { margin-bottom }` and `hr { margin }` (section heading -> content,
  and major section dividers) needed no such trick since they're real, directly-selectable
  tags already touched by the typography rule above. The one place Python changed:
  `upload_panel.py`'s "N document(s) ready" line is no longer `st.markdown("**...**")` but a
  raw `<p class="idp-group-heading"><strong>...</strong></p>` — chosen specifically because
  this is one of the few spacing transitions with no stable native selector to hook via
  `:has()`, and the class gives it an exact, scoped margin-bottom instead. Keep visually
  verifying any future spacing tweak here with real screenshots (or measured bounding-box
  gaps via Playwright) rather than trusting the CSS alone — adjacent block-level margins can
  collapse to the larger value instead of summing, which silently no-ops a naive margin
  addition; this only reliably avoids collapsing because Streamlit's vertical blocks are flex
  containers (`direction="column"` on `[data-testid="stVerticalBlock"]`), where sibling
  margins don't collapse and instead add on top of the flex `gap` as intended.
- **The Left/Right panel gap doesn't come from `st.columns()`'s `gap` value alone.** `app.py`
  passes `gap="large"` to `st.columns([1, 1.4], ...)`, but that Streamlit preset computes to
  `64px` (4rem) — measured directly, not assumed — which is wider than intended. `theme.py`
  pins the real value with `[data-testid="stHorizontalBlock"] { gap: 2rem !important; }`,
  overriding Streamlit's own emotion-generated gap class. If `gap="large"` is ever removed
  from the `st.columns()` call, this rule still applies on its own (it doesn't depend on that
  parameter being set) — but keep both in sync conceptually since the CSS comment explains
  itself by referencing the Python-side `gap="large"` call.
- **The Batch Summary KPI cards are custom HTML (`_kpi_card` in `results_panel.py`), not
  `st.metric`.** `st.metric` was the original implementation but couldn't render a two-tone
  value like "3 / 3" (the slash needs to be visually lighter than the numbers) or a
  description line under the number, so it was replaced outright — the `[data-testid="stMetric*"]`
  CSS rules that used to live in `theme.py` are gone too, replaced by `.idp-kpi-*`. Before that
  replacement, `[data-testid="stMetricValue"]` needed `white-space: normal` and a smaller
  `font-size` because Streamlit's default metric value font clipped a longer string (e.g. "0
  Variances") to "0 Varian..." inside a 3-column tile — this was caught by an actual rendered
  screenshot, not just a compile check. CSS targeting Streamlit internals should always be
  visually verified, not just assumed correct from the selector name. Prefer verifying with a
  live screenshot (Playwright/chromium) over guessing at
  `data-testid` behavior, since these are version-sensitive and Streamlit doesn't guarantee
  their stability across releases.
- **`st.expander` labels render as Markdown — watch for asterisks.** `_mask_tin` in
  `results_panel.py` produces strings like `***-**-1234` (SSN) or `**-***1234` (EIN) for
  display in an expander label; raw asterisks there get parsed as bold/italic markup and
  mangle into garbage (`*--1234`). Fixed by backslash-escaping every `*` in the masked
  output. Any other string built for
  an `st.expander`/`st.button` label needs the same care if it can contain `*`, `_`, or `` ` ``.
- **`st.expander(expanded=...)` must be pinned to session state if anything inside it
  triggers a rerun.** The Customer Reconciliation cards' "Show Raw Extracted JSON" `st.toggle` lives
  inside the same expander it's supposed to affect; toggling it triggers a script rerun, and
  `st.expander` resets to collapsed on every rerun unless you explicitly pass
  `expanded=st.session_state.get(toggle_key, False)`. Without this, flipping the toggle on
  visually snaps the card shut, hiding the very content just requested. This is a general
  Streamlit gotcha, not specific to this feature — same pattern applies anywhere a widget lives
  inside a container that has its own open/closed state.
- **`st.file_uploader`'s dropzone copy ("Drag and drop files here", the format/size line,
  "Browse files") has no Python-level override** — it's rendered natively with fixed wording.
  To show custom copy ("Drop tax documents here", a compact "PDF · PNG · JPG · Max 10 MB"
  line), `theme.py` targets the real DOM structure (verified via a live Playwright DOM dump,
  not guessed): `[data-testid="stFileUploaderDropzoneInstructions"]` wraps the icon `<svg>`
  and a `<div>` containing two `<span>`s (primary text, then size/format text). Each span is
  collapsed with `font-size: 0` and a `::after { content: "..." }` supplies the replacement —
  this keeps the original text in the DOM (so it's not a totally inaccessible hack) while
  visually showing different copy. The format/size line's `content` is **not** hardcoded in
  the static CSS block — `_upload_hint_text()` builds it from `config.ALLOWED_EXTENSIONS` /
  `config.MAX_UPLOAD_SIZE_MB` at call time and it's injected as a small separate single-line
  `<style>` string in `inject_custom_theme()`, so the displayed limit can't drift from the
  real one if either config value ever changes.
- **A CSS string built inside an indented Python function can silently render as visible
  text, not styles.** `inject_custom_theme()`'s dynamic hint-text rule is deliberately built
  as one single-line string, not a multi-line triple-quoted block. A multi-line string
  written inside a function body inherits that function's 4-space indentation on every line;
  `st.markdown` parses its input as Markdown *before* treating `unsafe_allow_html` content as
  raw HTML, and CommonMark treats a 4-space-indented block as a fenced code block — so the
  `<style>...</style>` tag prints as literal on-page text instead of being parsed as CSS. Hit
  this exact bug once already (the whole CSS rule appeared as a paragraph at the top of the
  page, and the dropzone's second text line silently vanished because `font-size:0` still
  applied with no `::after` content to replace it). The static `_CSS` block avoids this only
  because it's a module-level constant starting at column 0 — any *new* CSS built inside a
  function must either stay single-line or go through `textwrap.dedent()`.

## Run commands

```bash
# one-time setup
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in ANTHROPIC_API_KEY (required) and, optionally,
                        # SLACK_BOT_TOKEN/SLACK_CHANNEL for per-document Slack alerts

# run the app
streamlit run app.py
```

For a CSS/theming change, a compile check is not enough — visually verify with a real
screenshot. `playwright` + a headless Chromium aren't in `requirements.txt` (they're a QA-only
tool, not a runtime dependency), but can be installed ad hoc into the venv:
```bash
pip install playwright && playwright install chromium
```
Then drive the running app (`streamlit run app.py --server.headless true`) with
`playwright.sync_api`, screenshot it, and read the image back — this is how the two bugs in
the "Theming" section above (`stMetricValue` truncation, `st.expander` Markdown-mangling
`_mask_tin`'s asterisks) were actually caught; neither would show up in `py_compile` or a
scripted reconciliation test.

No test suite exists yet. Sanity-check changes with:
```bash
python -m py_compile app.py src/*.py src/ui/*.py
```

## Security & execution handling rules

- **Credentials load from environment only.** `src/config.py` reads `ANTHROPIC_API_KEY`,
  `CLAUDE_MODEL`, `SLACK_BOT_TOKEN`, `SLACK_CHANNEL`, `SMTP_HOST`, `SMTP_PORT`,
  `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`, `CHASER_EMAIL_OVERRIDE`, and
  `APP_BASE_URL` via `python-dotenv` / `os.getenv`. Never add a raw API key/token/password
  text input to the UI, never hardcode one, never log one.
- **`.env` is gitignored.** Only `.env.example` (placeholder values) is committed.
- **Nothing is persisted outside `st.session_state`, but there are now three deliberate,
  narrowly-scoped outbound calls — not one.** Uploaded documents, rendered images, extracted
  PII/TINs, and reconciliation results still live only in `st.session_state` for the life of
  the browser session — no disk write or database anywhere. The three outbound calls, each
  with its own privacy boundary (don't conflate them when changing one):
  1. `slack_notifier.notify_document_outcome` (IDP workflow, wired into
     `results_panel.py`'s per-document loop) — **only** filename, detected type, and audit
     status label. Never a TIN/SSN/EIN, name, or dollar amount.
  2. `slack_notifier.post_chaser_email` (Document Chaser, wired into `chaser_panel.py`'s
     `_run_batch`) — a drafted reminder email, which by necessity names the client and their
     missing/mismatched document types. Still never a TIN/SSN/EIN or dollar amount. See
     `slack_notifier.py`'s module docstring and the Document Chaser section above.
  3. `email_sender.send_email` (Document Chaser's "Approve & Send", opt-in per click, not
     automatic) — sends the same drafted-or-edited subject/body as a real email, to
     `config.CHASER_EMAIL_OVERRIDE` only (see the Document Chaser section's note on why), via
     whatever SMTP account `.env` configures.
  All three are optional and best-effort: a missing config, bad credentials, or network
  error is caught inside `slack_notifier.py`/`email_sender.py` and surfaced as a UI
  warning/error, never raised — one failed send can't interrupt anything else. If you widen
  what any of these three sends, or add a fourth outbound integration, update the sidebar's
  privacy card wording (`.idp-privacy-card` markup in `src/ui/sidebar.py`, styled in
  `theme.py`) to match reality — it's a compact custom HTML card, not a native `st.info`,
  precisely so its size/typography could be tuned independently of every other alert in the
  app. Keep the wording short (title + one-line italic subtitle + one short sentence) — it
  was deliberately condensed from a taller `st.info` paragraph, and ballooning it back into a
  paragraph defeats the point of the redesign.
- **Upload size is enforced twice:** `.streamlit/config.toml` (`server.maxUploadSize = 10`)
  caps it at the platform level, and `upload_panel.py` re-checks `uploaded_file.size` against
  `config.MAX_UPLOAD_SIZE_BYTES` so the limit holds even if the config file is later changed.
- **Processing timeout is enforced per document, in `extraction.py`.** Each Claude vision call
  runs inside its own `ThreadPoolExecutor` with
  `future.result(timeout=config.PROCESSING_TIMEOUT_SECONDS)` (default 30s). A timeout raises
  `ExtractionTimeoutError`, caught by `_process_document` in `results_panel.py` and recorded
  as that document's error — it does not abort the rest of the batch. Note: a 30s-per-document
  budget means an N-document batch can take up to N×30s in the worst case; there's no overall
  batch-level timeout or parallelism today (`render_results_panel` processes the list
  sequentially). Python also cannot forcibly kill a blocking thread, so an individual timed-out
  HTTP call may keep running in the background — acceptable for this demo's single-user scope,
  but worth revisiting (parallel processing, an async/cancellable HTTP client, or a batch-level
  cap) if this becomes a production service or batches grow large.
- **Exception handling is centralized at the UI boundary.** Pipeline code raises typed
  exceptions from `src/exceptions.py`; `app.py`'s panels (`upload_panel.py`,
  `results_panel.py`) are the only places that catch them and render `st.error`. Don't let
  raw tracebacks reach the Streamlit UI — if you add a new pipeline module, raise
  `IDPBaseError` subclasses from it rather than bare exceptions.
- **Model output is never trusted blindly.** `extraction.py` parses the LLM's JSON response
  defensively (strips markdown fences, extracts the outermost `{...}`) and then validates it
  against the per-form-type Pydantic schema (`Form1099NEC`, `Form1099Misc`, `FormW2`, or
  `FormK1`) before it reaches the UI or the reconciliation engine. Validation failures (e.g. a
  negative amount on a form where that's not allowed) raise `ExtractionError`, not a silent
  pass-through.

## LiteLLM + Anthropic gotchas (hit these once already, don't relearn them)

- **`CLAUDE_MODEL` must carry the `anthropic/` provider prefix** (e.g.
  `anthropic/claude-sonnet-5`), or LiteLLM raises `BadRequestError: LLM Provider NOT
  provided` — it can't infer the provider from a bare model id.
- **Org-level API keys can fail with a workspace-scoping error** ("This API key is not
  scoped to a workspace..."). Fix is account-side: generate the key from a specific
  workspace in the Anthropic Console (Settings → Workspaces → the workspace → API Keys),
  not from the org root. No code change needed once the key is workspace-scoped.
- **Dated model snapshots get retired.** `claude-3-5-sonnet-20241022` is gone from current
  accounts; `GET https://api.anthropic.com/v1/models` (with your key) lists what's actually
  available before assuming a model id still exists.
- **`temperature` is rejected by newer model generations** ("`temperature` is deprecated for
  this model"). The `_call_claude_vision` request in `extraction.py` intentionally omits it —
  don't re-add it without checking the target model supports it.
- **"Your credit balance is too low to access the Anthropic API"** is an account billing
  issue, not a code bug — the Anthropic account behind `ANTHROPIC_API_KEY` has run out of
  prepaid credits. Every document in a batch will fail extraction identically until this is
  fixed. Fix is account-side only: Anthropic Console → Plans & Billing → add a payment
  method / purchase credits; the same key starts working again immediately once credits are
  added, no code change or restart needed.

## Known gaps / open questions (update as resolved)

- Only the first rendered page of a multi-page upload is sent to the vision model
  (`results_panel.py` uses `base64_images[0]`). Multi-page packets aren't handled yet.
- Reconciliation matches on exact name string equality (recipient name for 1099-NEC/1099-MISC,
  employee name for W-2) — no fuzzy matching for typos/OCR noise between the document and the
  ledger.
- `FormW2.tax_year` isn't checked against the payroll ledger — `reconcile_w2` only compares
  wages and employer EIN (the payroll ledger has no `tax_year` column). `reconcile_1099_nec`
  and `reconcile_1099_misc` both check tax year via the `_tax_year_mismatch` helper in
  `reconciliation.py`, which compares as strings since `tax_year` is a loosely-typed
  `Optional[str]` on every schema now. Revisit if W-2 needs the same check.
- No way for the user to override a misclassified document. If the model detects the wrong
  form type (or a genuinely ambiguous/low-quality scan), the only recourse today is re-running
  extraction on a clearer image — there's no "this is actually a W-2" correction control.
- Batch processing is sequential and has no batch-level size cap or progress bar beyond the
  spinner — a large batch just runs longer (see the timeout note above).
- No entity-resolution across different taxpayer IDs. If a business's 1099 is filed under its
  own EIN (not the owner's personal SSN), it will never group with that owner's personal W-2 —
  by design (see the TIN-grouping note above), but there's no client/entity roster to bridge
  that gap even if a CPA firm wanted the linked view. Would need an explicit mapping table.
- The sidebar's "Load Sample Document" only loads one sample at a time. To demo the customer-
  grouping feature (e.g. John Doe's W-2 + 1099-NEC merging into one card) via the sample
  loader, both samples need loading and extracting one at a time in the same session — the
  loader itself wasn't extended to multi-select. Real multi-file upload already supports this.
- No automated test suite yet.
- Slack notifications are sent synchronously, one `chat.postMessage` call per document,
  inline in the same extraction loop (see the "Slack notifications fire per-document" design
  note above) — a slow or unreachable Slack API adds that latency directly to each document's
  processing time (though a failure itself doesn't raise/block, per `slack_notifier.py`'s
  design). No retry, queue, or batching. Fine for this demo's single-user scope; revisit
  (e.g. fire-and-forget via a background thread) if batches grow large or Slack reliability
  becomes a problem.
- **Document Chaser has a fixed, hardcoded roster of 4 clients** (`chaser_data.CLIENT_CHECKLISTS`)
  — no UI to add/edit a client or their checklist, no persistence of chaser results across a
  session restart (same session-state-only lifetime as the rest of the app). Fine for the
  current demo scope; would need a real client/checklist data store to go further.
- **Document Chaser's real email send needs SMTP credentials that aren't filled in by
  default.** `email_sender.py`/"Approve & Send" are fully built and wired, but
  `SMTP_USERNAME`/`SMTP_PASSWORD`/`SMTP_FROM_EMAIL` ship blank in `.env.example` (and the
  real `.env` until someone fills them in) — until they're set, every "Approve & Send"
  predictably fails with "Email sending not configured," which is the intended fallback, not
  a bug. Needs a Google Workspace App Password (demo) or equivalent.
- **Every Document Chaser send is hardcoded to one override address** (`CHASER_EMAIL_OVERRIDE`)
  since the demo roster has no real client addresses — see the Document Chaser section's note
  on this. Giving `CLIENT_CHECKLISTS` entries real addresses and removing the override is a
  prerequisite for any real client-facing use.
- **Document Chaser re-extracts every file in every client folder on every click** of "Check
  Documents & Email Clients" — no caching keyed on file content/mtime, so re-running the scan
  re-spends a full Claude vision call per file every time, same per-document ~30s timeout
  budget as the main IDP workflow. Fine for 4 small demo folders; would need caching to scale.
