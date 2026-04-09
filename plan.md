Here is your **final improvement context (MD)**

---

# AI Claim Report — Final Improvement Context

## Goal

Generate a **clean, structured, consistent AI claim report**
without recomputation and with correct field mapping.

---

# 1. Fixed Report Header (Always Static)

These values must **not come from AI or OCR**

### Title

```
HEALTH CLAIM
Assessment Sheet
```

### Generated Line

```
Generated: {current_datetime} | Doctor: {logged_in_user_name}
```

Example:

```
Generated: 3/27/2026, 5:57:59 PM | Doctor: Sapna
```

Source:

- datetime → server time
- doctor → current portal logged user

---

### Company Name (Always Fixed)

```
Medi Assist Insurance TPA Pvt. Ltd.
```

Never extract from document.

---

# 2. Claim Type Default

If not found in documents:

```
Claim Type = Reimbursement
```

Override only if explicitly found:

- cashless
- corporate
- network

---

# 3. Hospital Name Extraction (Generic Rule)

If hospital missing:

Check in order:

1. Page header (top 20%)
2. Largest uppercase text
3. Contains:
   - HOSPITAL
   - CLINIC
   - MEDICAL
   - CENTER

Ignore:

- patient name
- doctor name

Example detected:

```
SECOND LIFE HOSPITAL
```

---

# 4. Treating Doctor Extraction

Search patterns:

- DR.
- Dr.
- Consultant
- Treating doctor
- Physician

Extract nearest name.

Example:

```
CONSULTANT: DR. DESHPANDE
```

Result:

```
Dr. Deshpande
```

---

# 5. Patient Name Extraction

Only accept if near:

- Patient Name
- Insured
- Name:

Never from:

- header
- letterhead
- footer

---

# 6. Diagnosis Extraction Priority

Order:

1. "Diagnosis:" label
2. Discharge summary diagnosis
3. Lab-confirmed diagnosis
4. Ignore complaints

Correct:

```
MP Vivax positive with LRTI
```

Wrong:

```
fever cough weakness
```

---

# 7. Optimized AI Pipeline (Final)

## Step 1 — Extraction

Skip if exists

## Step 2 — Structured Data

Skip if exists

## Step 3 — Medicine Extraction

Skip if exists

## Step 4 — Checklist

Skip if fresh

## Step 5 — AI Reasoning

Always run

## Step 6 — ML Scoring

Always run

Outputs:

- decision
- confidence
- risk score

## Step 7 — Final Report Generation

Generate HTML with:

- header (fixed)
- claim info
- diagnosis
- investigations summary
- treatment summary
- checklist result
- AI decision
- confidence
- risk score
- final recommendation

---

# 8. Skip Logic (Performance)

Skip when already available:

| Step         | Skip Condition                 |
| ------------ | ------------------------------ |
| Extraction   | extraction exists              |
| Structured   | structured exists              |
| Medicine     | medicine exists                |
| Checklist    | checklist fresh                |
| AI reasoning | never skip                     |
| ML scoring   | never skip                     |
| Report       | regenerate if decision changed |

---

# 9. Final Report Must Contain

Header:

- Title
- Generated
- Company

Claim Info:

- Claim no
- Claim type
- Hospital
- Doctor

Medical:

- Diagnosis
- Investigations summary
- Treatment summary

AI:

- Decision
- Confidence
- Risk score

Final:

- Conclusion
- Recommendation

---

# Final Result

Run AI should:

- not re-extract
- not recompute
- fill missing fields
- generate report
- attach AI decision
- attach confidence
- attach risk score

Fast + consistent + correct.
