# The Future of Everything is Lies, I Guess: New Jobs

### Table of Contents

This is a long article, so I've broken it up into a series of posts, listed below. You can also read the full work as a [PDF](https://aphyr.com/data/posts/411/the-future-of-everything-is-lies.pdf) or [EPUB](https://aphyr.com/data/posts/411/the-future-of-everything-is-lies.epub).

*Previously: Work.*

As we deploy ML more broadly, there will be new kinds of work. I think much of
it will take place at the boundary between human and ML systems. *Incanters*
could specialize in prompting models. *Process* and *statistical engineers*
might control errors in the systems around ML outputs and in the models
themselves. A surprising number of people are now employed as *model trainers*,
feeding their human expertise to automated systems. *Meat shields* may be
required to take accountability when ML systems fail, and *haruspices* could
interpret model behavior.

## [Incanters](https://aphyr.com#incanters)

LLMs are weird. You can sometimes get better results by threatening them, telling them they’re experts, repeating your commands, or lying to them that they’ll receive a financial bonus. Their performance degrades over longer inputs, and tokens that were helpful in one task can contaminate another, so good LLM users think a lot about limiting the context that’s fed to the model.

I imagine that there will probably be people (in all kinds of work!) who
specialize in knowing how to feed LLMs the kind of inputs that lead to good
results. Some people in software seem to be headed this way: becoming *LLM
incanters* who speak to Claude, instead of programmers who work directly with
code.

## [Process Engineers](https://aphyr.com#process-engineers)

The unpredictable nature of LLM output requires quality control. For example,
lawyers [keep getting in
trouble](https://www.damiencharlotin.com/hallucinations/) because they submit
AI confabulations in court. If they want to keep using LLMs, law firms are
going to need some kind of *process engineers* who help them catch LLM errors.
You can imagine a process where the people who write a court document
deliberately insert subtle (but easily correctable) errors, and delete
things which should have been present. These introduced errors are registered
for later use. The document is then passed to an editor who reviews it
carefully without knowing what errors were introduced. The document can only
leave the firm once all the intentional errors (and hopefully accidental
ones) are caught. I imagine provenance-tracking software, integration with
LexisNexis and document workflow systems, and so on to support this kind of
quality-control workflow.

These process engineers would help build and tune that quality-control process: training people, identifying where extra review is needed, adjusting the level of automated support, measuring whether the whole process is better than doing the work by hand, and so on.

## [Statistical Engineers](https://aphyr.com#statistical-engineers)

A closely related role might be *statistical engineers*: people who
attempt to measure, model, and control variability in ML systems directly.
For instance, a statistical engineer could figure out that the choice an LLM
makes when presented with a list of options [is influenced
by](https://arxiv.org/html/2506.14092v1) the order in which those options were
presented, and develop ways to compensate. I suspect this might look something
like psychometrics—a field in which psychologists have gone to great lengths
to statistically model and measure the messy behavior of humans via indirect
means.

Since LLMs are chaotic systems, this work will be complex and challenging: models will not simply be “95% accurate”. Instead, an ML optimizer for database queries might perform well on English text, but pathologically on timeseries data. A healthcare LLM might be highly accurate for queries in English, but perform abominably when those same questions are presented in Spanish. This will require deep, domain-specific work.

## [Model Trainers](https://aphyr.com#model-trainers)

As slop takes over the Internet, labs may struggle to obtain high-quality
corpuses for training models. Trainers must also contend with false sources:
Almira Osmanovic Thunström demonstrated that just a handful of obviously fake
articles 1 could cause Gemini, ChatGPT, and Copilot to inform
users

[about an imaginary disease with a ridiculous name](https://www.nature.com/articles/d41586-026-01100-y). There are financial, cultural, and political incentives to influence what LLMs say; it seems safe to assume future corpuses will be increasingly tainted by misinformation.

One solution is to use the informational equivalent of [low-background
steel](https://en.wikipedia.org/wiki/Low-background_steel): uncontaminated
works produced prior to 2023 are more likely to be accurate. Another option is
to employ human experts as *model trainers*. OpenAI could hire, say, postdocs
in the Carolingian Renaissance to teach their models all about Alcuin. These
subject-matter experts would write documents for the initial training pass,
develop benchmarks for evaluation, and check the model’s responses during
conditioning. LLMs are also prone to making subtle errors that *look* correct.
Perhaps fixing that problem involves hiring very smart people to carefully read
lots of LLM output and catch where it made mistakes.

In another case of “I wrote this years ago, and now it’s common knowledge”, a
friend introduced me to [this piece on Mercor, Scale AI, et
al.](https://nymag.com/intelligencer/article/white-collar-workers-training-ai.html),
which employ vast numbers of professionals to train models to do mysterious
tasks—presumably putting themselves out of work in the process. “It is, as
one industry veteran put it, the largest harvesting of human expertise ever
attempted.” Of course there’s bossware, and shrinking pay, and absurd hours,
and no union.[2](https://aphyr.com#fn-2)

## [Meat Shields](https://aphyr.com#meat-shields)

You would think that CEOs and board members might be afraid that their own jobs
could be taken over by LLMs, but this doesn’t seem to have stopped them from
using “AI” as an excuse to [fire lots of
people](https://www.cnbc.com/2026/03/14/meta-planning-sweeping-layoffs-as-ai-costs-mount-reuters.html).
I think a part of the reason is that these roles are not just about sending
emails and looking at graphs, but also about dangling a warm body [over the maws
of the legal
system](https://uscode.house.gov/view.xhtml?req=granuleid%3AUSC-prelim-title5-section8477&num=0&edition=prelim) and public opinion. You can fine an LLM-using corporation, but only humans can apologize or go to jail. Humans can be motivated by
consequences and provide social redress in a way that LLMs can’t.

I am thinking of the aftermath of the Chicago Sun-Times’ [sloppy summer insert](https://aphyr.com/posts/386-the-future-of-newspapers-is-lies-i-guess).
Anyone who read it should have realized it was nonsense, but Chicago Public
Media CEO Melissa Bell explained that they [sourced the article from King
Features](https://chicago.suntimes.com/opinion/2025/05/29/lessons-apology-from-sun-times-ceo-ai-generated-book-list),
which is owned by Hearst, who presumably should have delivered articles which
were not composed entirely of sawdust and lies. King Features, in turn, says they subcontracted the
entire 64-page insert to freelancer Marco Buscaglia. Of course Buscaglia was
most proximate to the LLM and bears significant responsibility, but at the same
time, the people who trained the LLM contributed to this tomfoolery, as did the
editors at King Features and the Sun-Times, and indirectly, their respective
managers. What were the names of *those* people, and why didn’t they apologize
as [Buscaglia](https://www.404media.co/chicago-sun-times-prints-ai-generated-summer-reading-list-with-books-that-dont-exist/) and Bell did?

I think we will see some people employed (though perhaps not explicitly) as
*meat shields*: people who are accountable for ML systems under their
supervision. The accountability may be purely internal, as when Meta hires
human beings to review the decisions of automated moderation systems. It may be
external, as when lawyers are penalized for submitting LLM lies to the court.
It may involve formalized responsibility, like a Data Protection Officer. It
may be convenient for a company to have third-party subcontractors, like
Buscaglia, who can be thrown under the bus when the system as a whole
misbehaves. Perhaps drivers whose mostly-automated cars crash will be held
responsible in the same way—Madeline Clare Elish calls this concept a [moral
crumple
zone](https://www.researchgate.net/publication/351054898_Moral_Crumple_Zones_Cautionary_Tales_in_Human-Robot_Interaction).

Having written this, I am suddenly seized with a vision of a congressional
hearing interviewing a Large Language Model. “You’re absolutely right, Senator.
I *did* embezzle those sixty-five million dollars. Here’s the breakdown…”

## [Haruspices](https://aphyr.com#haruspices)

When models go wrong, we will want to know why. What led the drone to abandon
its intended target and detonate in a field hospital? Why is the healthcare
model less likely to [accurately diagnose Black
people](https://news.umich.edu/accounting-for-bias-in-medical-data-helps-prevent-ai-from-amplifying-racial-disparity/)?
How culpable should the automated taxi company be when one of its vehicles runs
over a child? Why does the social media company’s automated moderation system
keep flagging screenshots of Donkey Kong as nudity?

These tasks could fall to a *haruspex*: a person responsible for sifting
through a model’s inputs, outputs, and internal states, trying to synthesize an
account for its behavior. Some of this work will be deep investigations into a
single case, and other situations will demand broader statistical analysis.
Haruspices might be deployed internally by ML companies, by their users,
independent journalists, courts, and agencies like the NTSB.

\*Next: [Where Do We Go From Here?](https://aphyr.com/posts/420-the-future-of-everything-is-lies-i-guess-where-do-we-go-from-here)

- When I say “obviously”, I mean the paper included the phase “this entire paper is made up”. Again, LLMs are idiots.

  [↩](https://aphyr.com#fnref-1)
- At this point the reader is invited to blurt out whatever screams of “the real problem is capitalism!” they have been holding back for the preceding twenty-seven pages. I am right there with you. That said, nuclear crisis and environmental devastation were never limited to capitalist nations alone. If you have a friend or relative who lived in (e.g.) the USSR, it might be interesting to ask what they think the Politburo would have done with this technology.

  [↩](https://aphyr.com#fnref-2)
