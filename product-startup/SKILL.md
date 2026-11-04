---
name: product-startup
description: >
  Create and prepare a software product using practical validation, MVP,
  branding, domain-cost, service-selection, launch, and early-operations methods.
  Use when starting a product or extending its setup workflow. Not for evaluating
  a company as an investment or employer; use startup-analysis for that.
---

# Product Startup

Help the user turn a product idea into a small, usable product and its minimum launch setup. Work in the existing project and honor decisions the user has already made.

## Workflow

1. **Frame and validate the product.** Identify the user, their problem, the main job the product should do, first-release scope, and platform constraints. Name the riskiest assumption and choose a low-cost way to test it before committing to substantial build work or paid services.
2. **Confirm the name and brand.** Offer a short list with clear differences. Check obvious naming conflicts across public product names, app stores, package/repository namespaces, and domains. Treat public searches as preliminary, not legal trademark clearance. Once the user chooses, use consistent casing in the app display name, README, and project description. Keep internal IDs and repository paths stable unless the user asks to change them.
3. **Research a domain.** Use the registrar the user chooses; use Cloudflare Registrar when requested. Compare first-year and renewal prices, registration term, extension, and the registrar's displayed availability. Say when availability is only a search result and recheck before checkout. Record a candidate separately from a registered domain.
4. **Plan and onboard required services.** Inspect the project for existing integrations first. List only services required for the agreed product scope, with purpose, account owner, price or free-tier limits, renewal/billing, data handled, permissions, and setup dependencies. Separate code dependencies from external accounts and services. Before onboarding, confirm the chosen provider and plan with the user; store credentials only in the project's established secret mechanism.
5. **Set up the minimum product.** Reuse the project's framework and conventions. Check current official documentation for APIs or pricing that may have changed. Implement the smallest vertical slice that makes the product usable, and update the README with how to run it and which setup items are still candidates.
6. **Prepare launch and early operations.** For the chosen release path, check only the relevant items: deployment, DNS and HTTPS, backups, monitoring, cost alerts, rollback, and a way to receive user feedback. Define one observable first-release success measure. After launch, use feedback and that measure to choose the next small improvement.
7. **Keep the workflow current.** When the user adds a product-setup lesson or step, incorporate only the confirmed, reusable guidance here. Keep app-specific choices in that app's README or decision file rather than turning them into universal rules.

## Methods and decision rules

### Validate before spending

- Use a Jobs-to-be-Done lens: who is trying to make what progress, in which situation, and what they use today.
- Write one testable hypothesis: “We believe [user] has [problem] and will [observable behavior] when offered [solution].”
- Separate evidence from assumptions. Prioritize the assumption with high impact and low confidence, and test that one first.
- Choose the cheapest experiment that can observe the relevant behavior: a focused user conversation for problem discovery, a clickable prototype for workflow comprehension, or a manual/concierge trial for willingness to repeat.
- Before testing, state what will be observed and what result would change the plan. Set thresholds to the product and sample; do not invent universal user-count or conversion targets. If evidence is weak, keep the conclusion uncertain.
- Define the MVP as one end-to-end path that delivers the promised user outcome. Defer secondary workflows, broad settings, and integrations until evidence supports them.

### Compare names and brand options

Use a short table to compare candidates on:

- Fit with the product's main user outcome.
- Pronunciation, spelling, and memorability.
- Distinctiveness from existing products and tools.
- Fit across app title, repository/package namespace, app marketplace, and domain.
- Conflicts or uncertainties found in public searches.

Do not choose a name only because its domain is available. Check exact and similar names. Public search is not legal trademark clearance. Present a small shortlist and let the user choose.

### Compare domains by total cost and status

For each candidate, record the full domain, TLD, registrar, registration term, first-term price, renewal price, mandatory fees, and check date. Compare a stated ownership horizon:

Total cost = first-term price + renewal price × remaining years + mandatory fees

Keep introductory discounts separate from renewal cost. Consider audience fit and registration restrictions as well as price. Track status as candidate, search result says available, registry-confirmed, or registered. A search result is not a reservation; recheck availability immediately before checkout.

### Select and onboard services

Inspect the repository and existing integrations first. Build a compact service matrix:

| Field | Record |
|---|---|
| Service and phase | What it does and when the product needs it |
| Necessity | Required for the first release or optional later |
| Owner | Who manages the account and renewal |
| Cost | Free-tier limits, current price, renewal or usage charges |
| Data and access | Data sent, permissions granted, credentials/scopes needed |
| Exit path | Export, backup, or replacement option |

Prefer the smallest set of services that covers the first release. Recommend a provider only after checking fit with the stack, data needs, and cost constraints. Confirm the exact provider and plan before onboarding. Do not create accounts, enable integrations, select paid plans, or issue credentials until the user approves the exact service and scope.

### Prepare launch and review early use

Check only items relevant to the product:

- A clean install/build can complete the primary user journey.
- Production settings, DNS, and HTTPS are correct when applicable.
- User data can be backed up and recovered when the product stores it.
- Monitoring can expose failures; cost alerts cover metered services.
- A rollback or disable path exists for risky releases.
- Privacy notices, terms, or support contact are present when data collection or payment requires them.

Choose one user-outcome metric and one guardrail. Agree on a baseline or target and review date with the user; do not invent targets. After launch, combine the measure with direct feedback and prioritize the next change by user impact, evidence, and effort rather than raw feature count.

## External actions

Researching, comparing, or writing a setup plan does not authorize registering a domain, creating an external account, choosing a paid plan, or enabling a service. Before any such action, get the user's explicit approval for the exact service or domain, term, and cost. Do not enter credentials or create API keys as part of routine setup.

## Extend this skill

When the user brings a new product-setup issue, solve it first. Add a lasting instruction only when the lesson is reusable and confirmed; express it as the trigger, method, decision rule, and resulting record. Keep one-off product state in that project's documentation.
