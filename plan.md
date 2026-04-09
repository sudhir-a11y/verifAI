Yes — split view by role.

# Doctor / Auditor view (simple)

Only comparison panel — no cost.

```
AI vs ML Analysis
-------------------------
AI Decision: APPROVE
AI Confidence: 0.82

ML Decision: REJECT
ML Confidence: 0.76

Agreement: ❌
```

That's it.
No tokens, no model, no cost.

---

# Admin view (full cost summary)

Show everything:

```
AI vs ML Analysis
-------------------------
AI Decision: APPROVE
AI Confidence: 0.82

ML Decision: REJECT
ML Confidence: 0.76

Agreement: ❌
```

Then cost block:

```
AI Usage Summary
-------------------------
Model: GPT-4.1
Tokens: 1500
Cost: $0.0042
Step: Report Generation
```

---

# Admin (total claim cost)

```
Total AI Cost (Claim)
-------------------------
Extraction: $0.0021
Structuring: $0.0014
Reasoning: $0.0009
Report: $0.0042
-------------------------
Total: $0.0086
```

---

# Final UI layout

Doctor/Auditor:

```
Report
AI summary
AI vs ML panel
Checklist
```

Admin:

```
Report
AI summary
AI vs ML panel
AI usage breakdown
Total claim cost
Checklist
```

This is correct separation.
