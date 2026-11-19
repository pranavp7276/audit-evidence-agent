# Data dictionary

One section per source. Fill in as each dataset is loaded. The time-zone column is the most
important: say what zone each timestamp is in and **how you know** (documented, inferred from
data, told by organisers).

## Template

### <table> (<source system>)
- **What it is:**
- **Raw table:** `raw.<table>`   **Staging view:** `staging.<view>`
- **Grain:** one row per …
- **Natural key:**
- **Joins to:**
- **Known traps:**

| Column | Type in staging | Meaning | Time zone (and how we know) |
|---|---|---|---|
| | | | |

---

> All sections below describe the SYNTHETIC dataset (decisions D-008 to D-010). Zones are by design of
> the generator, not inferred from real data.

### d4_contact_log (D4)
- **Raw / staging:** `raw.d4_contact_log` / `staging.d4_contacts`. **Grain:** one row per contact attempt. **Key:** `contact_id`.
- **Joins to:** `d5` on account_id+channel; `d10` and `d11` on contact_id; `collector_roster`/`cert_register` on collector_id.
- Columns: contact_id, account_id, collector_id, channel (call/whatsapp/sms), contact_ts (**Asia/Kolkata**, naive), outcome
  (connected/no_answer/delivered), dues_disclosed (Y/N), template_id, recording_id.
- **Traps:** timestamps are IST, consent and verification are UTC. Extra same-day calls and out-of-hours calls are seeded.

### d5 (D5): consent registry
- **Raw / staging:** `raw.d5` / `staging.d5_consents`. **Grain:** one consent per account and channel. **Key:** `consent_id`.
- Columns: consent_id, account_id, channel, consent_ts (**UTC**, ends in Z), status, capture_source.
- **Traps:** some consents are captured after the first message (often only hours later, so comparing clock values
  without converting zones wrongly passes them); some accounts have no consent record.

### d10 (D10): recording store
- **Raw / staging:** `raw.d10` / `staging.d10_recordings`. **Grain:** one recording per connected call. **Key:** `recording_id`.
- Columns: recording_id, contact_id, account_id, recorded_ts (**Asia/Kolkata**), duration_sec, storage_uri.
- **Traps:** about 3% of connected calls have no recording.

### d11 (D11): identity verification
- **Raw / staging:** `raw.d11` / `staging.d11_verifications`. **Grain:** one verification per call where dues were disclosed. **Key:** `verification_id`.
- Columns: verification_id, account_id, contact_id, verified_ts (**UTC**), method, result (passed/failed).
- **Traps:** verification after disclosure, a failed verification followed by disclosure, or no row at all.

### d12 (D12): calling hours and frequency limits
- **Raw / staging:** `raw.d12` / `staging.d12_policy`. One row per parameter: calling_hours_start 08:00, calling_hours_end 19:00
  (exclusive), max_calls_per_day 3, notice_sla_business_days 5. Read these; never hard-code them.

### notice_dispatch
- **Raw / staging:** `raw.notice_dispatch` / `staging.notices`. **Grain:** one notice. **Key:** `notice_id`.
- Columns: notice_id, account_id, notice_type, borrower_state, trigger_date, dispatch_date, service_date (calendar dates, India).
- **Traps:** late service (more than 5 business days); a weekend or holiday can stretch calendar days without breaching.

### holiday_calendar
- **Raw / staging:** `raw.holiday_calendar` / `staging.holidays`. Columns: holiday_date, holiday_name, scope (national/state), state.

### collector_roster
- **Raw / staging:** `raw.collector_roster` / `staging.collectors`. 1,200 collectors. Columns: collector_id, collector_name, agency, state, status.

### cert_register
- **Raw / staging:** `raw.cert_register` / `staging.certifications`. Columns: cert_id, collector_id, cert_name, valid_from, valid_to
  (inclusive dates). **Traps:** certificates that expired before calls the collector made, and lapse-then-renew gaps.
