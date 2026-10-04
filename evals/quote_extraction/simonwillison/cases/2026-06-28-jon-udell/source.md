# “Doctor, it hurts when agents create unreviewable PRs.” “Don’t do that.”

I recently attended a talk, by an engineer at a large software company, on the topic of unreviewable PRs. The problem? When agents raise PRs with thousands of lines of LLM-written adds/deletes/edits, people can’t make sense of them. The solution? Throw more agents at the problem: reviewer agents that scan what coding agents have produced, identify problems, and triage them.

I don’t make software at industrial scale, so I can’t evaluate the claim that throughput gain justifies the absence of end-to-end human engagement. What I can say is that as I use [Bram](https://github.com/judell/bram) to bootstrap itself, I am fully engaged thanks to the workflow embodied in the tool.

Here’s the breakdown of languages in Bram.

| Language | Lines of code |
| --- | --- |
| Rust | 24,630 |
| JavaScript | 7,542 |
| XMLUI | 4,149 |
| Python | 3,152 |
| Markdown | 1,419 |
| XS (XMLUI) | 742 |
| Total | 42,805 |
| --- | --- |

Bram is a Tauri desktop app, Tauri’s native language is Rust, so Rust — a language I never touched before this project — dominates. I have yet to write a single line of Rust! But I read the Rust code that Claude Code and Codex write for me, as they write it. I understand the nature and purpose of that code, and I push back when things don’t smell right.

Bram’s workflow helps do that by breaking problems into small testable chunks and processing them in an orderly way. That’s hardly a novel idea. In the LLM era we are finding new reasons to honor old best practices. We’ve always said that documentation is an essential part of the product, for example, but we haven’t always made it so. Now that readers include both people and machines we invest more effort in the docs. Why not also invite LLMs to join us in conventional agile practices?

## Enriched local context

When we invite these new partners onboard, how do we orient them? Chat sessions build context that’s private to LLMs, not shared with a team of people and agents. Bram lifts that context into two kinds of shared spaces: the local worklist and the GitHub repository. On the local worklist you define a task or feature, iterate on its spec, do the task or build the feature, and iterate on outcomes. The worklist item lives in the local repo and, whether tracked or not, provides context shared between you and Claude Code, and maybe with Codex too. As shown here, it’s a one-click operation to switch between agents so one can weigh in on a plan or implementation written by the other. Here I’m about to bring in Claude as a relief pitcher.

[![](https://i0.wp.com/jonudell.info/images/tauri-subscribe-churn.png?w=656&ssl=1)](https://i0.wp.com/jonudell.info/images/tauri-subscribe-churn.png?ssl=1)

One of the delightful emergent properties of this system has been the evocative names that agents create for worklist items. Naming is famously hard. I could conjure a name like *startup-freeze-tail-fanout-diagnostics* on my own but these names aren’t public-facing, they are perfectly serviceable, there is no reason for me to bear the cognitive load of creating them.

Bram records a searchable history of worklist items so my agents and I can refer to them.

[![](https://i0.wp.com/jonudell.info/images/fanout-history-search.png?w=656&ssl=1)](https://i0.wp.com/jonudell.info/images/fanout-history-search.png?ssl=1)

Our human context windows can handle about five to seven things at a time, so I prune the worklist accordingly. If other things come up that bump the priority of *startup-freeze-tail-fanout-diagnostics* I can use the Drop button to clear it from the worklist. Then I can refind it on the History page, perhaps by searching for *fanout*, and ask the active agent to resurrect it as a new worklist item.

## ~~Human~~ Agent in the loop

I dislike the phrase “human in the loop” because it cedes authority to the machines. Let’s flip the narrative. It’s our loop, we work the same way we always have, now we recruit agents to join the team. An agent-assisted process need not be a black box that takes in prompts and emits features.

I’m reminded of a beautiful idea of Brian Marick’s that Ward Cunningham once implemented and demoed to me. Brian called it [visible workings](https://blog.jonudell.net/2008/03/04/ward-cunninghams-visible-workings/). Ward’s implementation made an Eclipse Foundation workflow visible. When the UI presented a form, it added an Explore button that you could use to inspect the business rule that motivated the form.

Let’s do agentic software development like that. Not as a loop we’ve been excluded from, instead as one we invite agents into.
