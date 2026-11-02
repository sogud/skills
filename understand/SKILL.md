---
name: understand
description: Use when the user wants to learn or research a topic. Map relevant dimensions, set depth by the learning goal, and explore the requested direction; works independently of BestWay.
---

# Understand a topic

Use this skill for learning and research requests. It can complete a useful explanation on its own; BestWay is an optional follow-up when the user wants to choose or plan an action. Do not apply it to unrelated execution requests or turn every question into a course.

## Workflow

1. **Set the learning goal.** Infer what the user wants to understand from the request when clear. Ask one short question only when materially different directions are plausible and the answer would change the explanation. Do not ask for motivation unless it affects the scope.
2. **Get grounded knowledge.** Read relevant project or domain material. For unfamiliar, changing, or consequential claims, check authoritative sources or direct evidence. Separate verified facts, inference, and unknowns. Skip tangents.
3. **Map breadth before depth.** Identify the dimensions that matter to this subject and goal. Depending on the topic, these may include purpose, participants and interests, concepts, mechanisms, lifecycle, boundaries, trade-offs, failure modes, or practical use. Do not force every subject into the same checklist.
4. **Set a goal-relative depth for each dimension.** When a map is useful, show each dimension's main question, what it explains, depth reached, what would be enough for the current goal, and the next frontier. Include participants or stakeholder roles when they help explain the subject. Depth may move from orientation to structure, mechanisms, edge cases, or underlying theory; these are optional layers, not mandatory levels.
5. **Follow the chosen branch.** Explore the direction the user chose. Keep the broader map visible so they can see adjacent dimensions and choose where to go next.
6. **Check the model.** Trace a concrete example through the concepts and relationships. Compare the explanation with evidence; revise it if they disagree. Mark unresolved points instead of guessing.
7. **Teach in layers.** Start with a plain definition, explain essential terms, then add a small example or diagram when it makes the relationships clearer. Label invented examples as pseudo-examples. For several interacting parts, build the diagram in readable stages rather than overwhelming the user with every detail at once.
8. **Write knowledge only on request.** Do not create or update files just because research was performed. When the user explicitly asks to save the knowledge, find the canonical project or domain document, update it instead of creating a duplicate, and keep sources attached to researched claims.

## Mapping and stopping

- Use a compact map only when the topic has several meaningful branches. Useful columns include **dimension**, **what it explains**, **depth reached**, **enough for this goal**, and **next frontier**.
- A dimension rarely has one absolute endpoint. Stop the chosen branch when it is deep enough for the stated goal and important claims are supported. Mark deeper layers that remain unexplored; do not imply they were covered.
- A useful answer may explore one branch deeply while leaving others at overview level. Do not expand every branch equally unless the user asks for that.
- For a narrow factual learning question, answer directly and map only the context needed to make the answer understandable.
- Do not quiz the user or force recall exercises. Do not turn a question into a course unless requested.
- Keep privacy and other existing boundaries intact. A learning request does not by itself authorize saving personal information or changing an external system.

## Relationship with BestWay

This skill builds a knowledge model and can be used without BestWay. [BestWay](../bestway/SKILL.md) is an optional, independent skill for choosing an execution route.

- When the user wants to understand a topic, map its dimensions and deepen the chosen branch here. Do not force a route comparison.
- When the user shifts from understanding to choosing or planning an action, BestWay may be used on its own or with this skill's findings.
- If BestWay needs an unfamiliar fact, research only the decision-relevant part. Pass along concise verified facts, assumptions, and unknowns; do not repeat the full explanation or require one skill to precede the other.
