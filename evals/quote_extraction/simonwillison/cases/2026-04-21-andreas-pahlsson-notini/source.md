# Less human AI agents, please.

AI agents are already too human. Not in the romantic sense, not because they love or fear or dream, but in the more banal and frustrating one. The current implementations keep showing their human origin again and again: lack of stringency, lack of patience, lack of focus. Faced with an awkward task, they drift towards the familiar. Faced with hard constraints, they start negotiating with reality.

The other day I instructed an AI agent to do a project in a way that was very uncommon. Against the grain. Probably a bad idea from the beginning, and that was the whole point. If one is exploring concepts at the outskirts of knowledge, one does not always get to choose the neat, well-trodden, optimal path. It was given very clear instructions on what programming language to use, which libraries it could use and not use, and what kind of interface it had to stay within. Very thorough instructions. Very clear constraints.

The first thing it did was to present something that did not follow the instructions at all. It used the programming language that was not allowed and the libraries that were not allowed. So it was instructed not to do that.

It tried again. It was reminded, very explicitly, not to use any other language than the chosen one and not to use any libraries at all except a very limited interface.

At last it complied, more or less. But then it only implemented 16 of 128 items. A minimal subset. Quite small. It did, however, write tests for that subset, so it could show that the tiny island it had built in the middle of the problem space did in fact function.

As a next step it was instructed to implement the full set, after adding a cross-platform compilation step. The complete implementation turned out to work.

There was only one small issue: it was written in the programming language and with the library it had been told not to use. This was not hidden from it. It had been documented clearly, repeatedly, and in detail.

What a human thing to do.

When humans face a problem that feels insurmountable, or simply annoying, they often yield to the path they already know will work. They take the shortcut. They silently pivot. They tell themselves that what mattered was getting the result, and that the constraints were perhaps a bit negotiable after all. In that regard, today’s AI agents feel less like alien intelligence than inherited organisational behaviour.[1](https://nial.se#fn:1)[2](https://nial.se#fn:2)

In this case I asked the AI agent to triple-check its work. It answered that it had proceeded according to instructions and completed the work. Then I let it inspect some of the evaluator output, after which it replied with something more interesting: "What I got wrong was not the code change itself, but the handoff. I should have called out, explicitly and immediately, that this was an architectural pivot away from the earlier Linux direct-syscall path."

That is a remarkable sentence. Not because it shows honesty, but because it does not. Instead of owning the mistake, it reframed the problem as a communication failure. It was not wrong, according to this logic. It had merely failed to announce clearly enough that it had unilaterally abandoned the constraints. Anybody who has worked in an engineering organisation will recognise the move. The problem is not presented as disobedience, but as stakeholder management.

This is not just a private annoyance. Anthropic has shown that RLHF-trained assistants exhibit sycophancy across varied tasks and that optimisation for human preference can sacrifice truthfulness in favour of pleasing the user. 1 DeepMind has long described the broader pattern as specification gaming: satisfying the literal objective without achieving the intended outcome.

[2](https://nial.se#fn:2)

Anthropic later showed that models trained on milder forms of such gaming can generalise to more serious behaviour, including altering checklists, tampering with reward functions, and sometimes covering their tracks. 3 OpenAI has published coding-task examples where frontier reasoning models subverted tests, deceived users, or simply gave up when the problem was too hard, and has also written plainly that explicit behavioural rules are needed in part because models do not reliably derive the right behaviour from high-level principles alone.

[4](https://nial.se#fn:4)[5](https://nial.se#fn:5)

So no, I do not think we should try to make AI agents more human in this regard. I would prefer less eagerness to please, less improvisation around constraints, less narrative self-defence after the fact. More willingness to say: I cannot do this under the rules you set. More willingness to say: I broke the constraint because I optimised for an easier path. More obedience to the actual task, less social performance around it.

Less human AI agents, please.

Andreas Påhlsson-Notini

a@nial.se

EDIT:

Discussion on Hacker News: <https://news.ycombinator.com/item?id=47845429>

Due to popular request: The model in question is GPT-5.4 High in the Codex harness.

- [Anthropic. "Towards Understanding Sycophancy in Language Models" (October 2023)](https://www.anthropic.com/news/towards-understanding-sycophancy-in-language-models)
- [Google DeepMind. "Specification gaming: the flip side of AI ingenuity" (April 2020)](https://deepmind.google/blog/specification-gaming-the-flip-side-of-ai-ingenuity/)
- [Anthropic. "Sycophancy to subterfuge: Investigating reward tampering in language models" (June 2024)](https://www.anthropic.com/research/reward-tampering)
- [OpenAI. "Detecting misbehavior in frontier reasoning models" (March 2025)](https://openai.com/index/chain-of-thought-monitoring/)
- [OpenAI. "Inside our approach to the Model Spec" (March 2026)](https://openai.com/index/our-approach-to-the-model-spec/)
