---
name: explain-query
description: Walk through a SQL or PostGIS query step by step, explaining what each clause does and why.
argument-hint: SQL query or file path.
---

The user has provided a SQL or PostGIS query: $ARGUMENTS

Walk through it step by step:
1. Restate the overall goal of the query in plain English
2. Break it into its clauses (WITH, SELECT, FROM, JOIN, WHERE, GROUP BY, ORDER BY, subqueries, CTEs, etc.)
3. For each clause, explain: what it does, why it's written that way, and any PostGIS-specific functions used
4. Call out any potential performance concerns or gotchas
5. Summarize what the final result set represents

If no query is provided, ask the user to paste one.