---
title: "Governed Routing With Receipts — When the Local Lane Consults the Frontier, and What It Costs"
date: 2026-06-18
author: Manav Sehgal
product: Foundation
stage: agentic
difficulty: advanced
time_required: "planned ~14 min read"
hardware: "NVIDIA DGX Spark"
tags: [routing, escalation, cost, observables, llama-cpp, openrouter, advisor, receipts, dgx-spark]
summary: "The Advisor's router is deterministic and observables-only: it escalates on detectable failure signals — a citation outside the retrieved set, a rank-sanity anomaly — never on vibes. Route bakeoffs at $0 and $0.0033, a no-egress gate for private state, and a receipt a script re-verifies."
status: upcoming
series: Machine that Builds Machines
---

The third piece of the Advisor trilogy: the governance layer between a trained local lane and the hosted frontier.

Planned coverage: the observables-only router (escalate on `citation_outside_retrieved`, rank-sanity margins, format failure — signals computable without labels) and its honest limitation (a wrong citation that outranks the right one is undetectable); the route bakeoff economics — local-only 28/28 at $0, frontier-in-the-loop 28/28 at $0.0033, with every hosted escalation carrying tier, provider, model, cost, and verdict; the data-policy gate that blocks private-state queries from egress entirely; and the §14 publish receipt — promotion as a script that reads tracked evidence and fails when a claim stops being supported, rendered as read-only cards in the Arena cockpit.

The through-line from [the refusal-floor piece](/articles/the-refusal-floor-is-trainable/): the weights carry the floor, the router narrows the remaining failure surface, and the receipt makes the whole decision auditable.
