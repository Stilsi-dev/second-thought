---
name: report
description: Assembles the final structured Decision Report from the domain draft, critic findings, and collected facts. Triggers last, after the critic skill and (for sensitive domains) human confirmation. Produces structured data only — rendering is left to the UI (A2UI-style separation, Day 2).
---

Purely deterministic assembly, no LLM call needed — the data has already been
reasoned about by the domain and critic skills. Keeping this templated (not
model-generated) means the final report can never hallucinate a number that
wasn't already verified upstream.
