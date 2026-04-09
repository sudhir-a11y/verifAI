# AI Brain UI — Minimal Plan

## legacy UI update app/web/

## Goal

Show AI “Brain” outputs in **Doctor + Auditor UI** with minimal changes.

---

# Where AI Runs

Trigger:

```
POST /claims/{id}/decide
```

Called from:

- Doctor page → "Run AI"
- Auditor page → "Run AI"

---

# Show These Fields (Minimal)

Display:

```
ai_decision
ai_confidence
risk_score
conflicts
final_decision
route
```

---

# Doctor UI (Minimal)

Add panel:

```
AI Decision
Confidence
Risk Score
Run AI button
Submit Doctor Decision
```

Doctor actions:

```
approve
reject
query
```

Doctor API:

```
POST /claims/{id}/doctor-verification
```

---

# Auditor UI (Minimal)

Add panel:

```
AI Decision
Confidence
Risk Score
Conflicts
Final Decision
Run AI button
```

Auditor actions:

```
approve
reject
query
```

Auditor API:

```
POST /claims/{id}/auditor-verification
```

---

# UI Flow

```
Open claim
   ↓
Run AI
   ↓
Show AI decision
   ↓
Doctor verifies
   ↓
Auditor verifies
   ↓
Final decision
```

---

# Decision Priority

```
auditor > doctor > AI
```

---

# Minimal UI Layout

```
[ AI Decision Box ]

Decision: QUERY
Confidence: 0.72
Risk Score: 0.61

Conflicts:
- AI approve vs GST invalid

[ Run AI ]

[ Doctor Decision ]
Approve | Reject | Query

[ Auditor Decision ]
Approve | Reject | Query
```

---

# Files to Update

Doctor UI

```
workspace.js
doctor page html
```

Auditor UI

```
auditor-qc.html
auditor-qc.js
```

React UI (later)

```
verifAI-UI/src/pages/ClaimReview.jsx
```

---

# Minimal Implementation Order

Step 1
Add Run AI button (doctor + auditor)

Step 2
Show AI fields

Step 3
Add doctor submit

Step 4
Add auditor submit

Done
