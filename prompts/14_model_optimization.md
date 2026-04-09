# AI Model Plan (Without MedGemma) — Final Implementation

## Goal

Implement cost-optimized AI stack using:

- DeepSeek OCR
- DeepSeek Reasoner
- GPT fallback

MedGemma will be added later without changing architecture.

---

# Final Architecture (Current)

```
DeepSeek OCR
     ↓
Extraction
     ↓
Rule Engine
     ↓
DeepSeek Reasoning (Primary AI)
     ↓
Risk Scoring
     ↓
Conflict Detection
     ↓
Decision Fusion
     ↓
GPT Fallback (only when needed)
     ↓
Doctor
     ↓
Auditor
     ↓
Final Decision
```

---

# Model Responsibilities

## Model 1 — DeepSeek OCR

Use for:

- prescription OCR
- discharge summary
- lab reports
- scanned documents
- handwritten notes

Do NOT use for:

- reasoning
- decision making

Output:

```
normalized_text
structured_entities
```

---

## Model 2 — DeepSeek Reasoner (PRIMARY AI)

This replaces MedGemma for now.

Use for:

- diagnosis validation
- treatment mismatch
- fake claim detection
- checklist reasoning
- medical logic validation
- admission necessity
- antibiotic misuse

Input:

```
normalized_text
rule_hits
structured_data
verification_flags
```

Output:

```
ai_decision
ai_confidence
ai_flags
ai_reason
```

---

## Model 3 — GPT (Fallback Only)

Use only when:

- conflicts detected
- ai_confidence < threshold
- doctor vs AI mismatch
- verification invalid + AI approve
- auditor escalation
- final explanation generation

Do NOT call GPT for every claim.

---

# Call Strategy (Important)

### Always call

DeepSeek OCR
DeepSeek Reasoner

### Conditional call

GPT only when:

```
conflicts exist
OR ai_confidence < 0.6
OR verification invalid
OR doctor override
```

---

# Decision Flow

```
rules_result
 + deepseek_ai
 + verification_flags
 → conflict_detector
 → confidence_aggregation
 → decision_fusion
 → optional GPT fallback
```

---

# GPT Fallback Logic

```
if ai_confidence > 0.75 and no conflicts:
    skip GPT

if conflicts:
    call GPT

if verification_invalid:
    call GPT

if doctor_vs_ai:
    call GPT
```

---

# Cost Optimized Pipeline

```
DeepSeek OCR (cheap)
     ↓
DeepSeek Reasoning (cheap)
     ↓
Rules (free)
     ↓
GPT only when needed
```

Expected:

- 80–90% fewer GPT calls
- 10x cost reduction

---

# Files to Implement

Create:

```
ai/
 ├── deepseek_reasoning.py
 ├── conflict_detector.py
 ├── confidence.py
 └── decision_engine.py
```

---

# DeepSeek Reasoning Prompt

```
You are medical claim fraud detection AI

Analyze:
- diagnosis
- treatment
- investigations
- billing
- verification flags

Return JSON:
decision
confidence
flags
reason
```

---

# Decision Engine Inputs

```
rules_result
ai_reasoning
verification_flags
doctor_decision
auditor_decision
```

---

# Decision Engine Output

```
final_decision
confidence
route
risk_score
conflicts
reason
```

---

# Routing Rules

```
high confidence approve → auto approve
high confidence reject → auto reject
conflicts → auditor review
low confidence → doctor review
verification invalid → query
```

---

# Future Upgrade (When MedGemma Ready)

Replace:

```
DeepSeek reasoning
```

With:

```
MedGemma reasoning
```

No other changes needed.

---

# Final Stack (Current)

Use:

DeepSeek OCR
DeepSeek Reasoner
GPT fallback

This is the final production plan.
