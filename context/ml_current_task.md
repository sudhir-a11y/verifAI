• Your ML model is not replacing the whole AI pipeline. It is a supervised final-decision helper built from your historical
doctor/auditor outcomes.

What it does

- It predicts the likely final claim decision from features already produced by your pipeline.
- The labels are things like approve, reject, need_more_evidence, manual_review.
- It is used as an additional signal inside the decision engine, not as the only source of truth.

You can see that in:

- backend/app/ml_decision/predictor.py
- backend/app/ml_decision/feature_engineering.py
- backend/app/api/v1/endpoints/claims.py:1293
- backend/app/ai/decision_engine.py:289

Why you built it

1. To learn from real doctor and auditor decisions.
   - Rules and LLM output are generic.
   - ML learns your team’s actual patterns from past cases.
2. To reduce dependence on expensive LLM calls for final decisioning.
   - Once trained, ML inference is cheap.
   - It can become a stable decision signal even when LLM confidence is noisy.
3. To improve consistency.
   - Doctors/auditors may repeatedly make similar decisions on similar cases.
   - ML captures that behavior and makes the pipeline more repeatable.
4. To support fusion, not blind automation.
   - Your code keeps the hierarchy: auditor > doctor > ML > AI.
   - So ML is one signal in the final fusion logic, not a fully autonomous replacement.

What data it uses
It uses engineered features such as:

- AI decision
- AI confidence
- verification results
- risk/conflict indicators
- structured claim fields

See:

- backend/app/ml_decision/feature_engineering.py
- backend/app/ml_decision/dataset_builder.py

What problem it solves
Without ML:

- you depend mostly on rules + LLM + human overrides

With ML:

- you add a cheap learned prediction from historical outcomes
- this helps ranking, triage, and final decision confidence

Important limitation
Right now ML does not save much cost by itself unless you actually use it to skip or reduce some LLM calls.
At the moment, it mainly improves decision fusion, not total billing.

In one line
You built the ML model to learn from past claim outcomes and provide a cheap, consistent final-decision signal that complements
rules, LLM reasoning, and human review.

If you want, I can next explain:

1. exactly what features go into the ML model
2. where in the /decide flow it influences the final result
3. whether the ML model is currently worth keeping or not
