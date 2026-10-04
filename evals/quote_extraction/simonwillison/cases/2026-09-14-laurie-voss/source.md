# We are all Product Engineers now

Just yesterday I published [a very long post](https://seldo.com/posts/nobody-pays-for-open-source-we-can-force-them-to/) about the economics of open source. As part of that argument, I mentioned that the cost of writing software has collapsed, and that meant the variables in the equation had changed for the first time in thirty years.

That led me off on a tangent that grew into this equally long post. I had a bunch of questions to answer. Has the cost of creating software really collapsed? Can I prove that? If the cost of actually producing code goes to zero, what parts of the job of “software developer” really remain? Where, in fact, is the entire industry of software going in the next decade?

You can see why I felt it needed a post of its own.

I’ve been circling this topic for a while now. In [early 2025](https://seldo.com/posts/ai-effect-on-programming-jobs/) I predicted AI would create many more programmers and that their jobs would look different, but I didn’t get into the details of how different, and also that was more than a year ago, an infinity in the compressed timeline of AI. In [March this year](https://seldo.com/posts/do-ai-enabled-companies-need-fewer-people/) I found companies substituting compute for labor at record rates. In [July](https://seldo.com/posts/ai-has-torched-the-market-for-junior-programmers/) I looked into labor statistics and found that the market for junior programmers had been savaged while the market for senior ones was fine, in fact growing.

This post is an attempt to build on those and make a forecast of where the industry is going in the next 10 years. Making a 10 year forecast of anything is of course a crazy thing to try to do, and especially about the business of software right now. To make it, I had to make two very big assumptions.

## Assumption 1: agents are going to eat the entire software development lifecycle

This assumption is based on the observation that agents are currently very good at writing code and mediocre at everything that comes after that: reviewing code, testing it, finding bugs, fixing bugs, deploying to production, monitoring, and scaling up. They suck at that stuff right now, but my assumption is that that’s a temporary state of affairs. There’s nothing structural about those things that prevents agents figuring out how to do that stuff. If you think I’m right about that, this post will be of interest, but if you think I’m wrong now is a good time to bail.

## Assumption 2: there is no upper bound to how much software we need

This one is if anything even more out on a limb. If you think I’m wrong about this you probably think software developers as a profession are doomed. I disagree.

I've made this argument before: look at the website of your dentist, your insurance company, your kid's school, or literally any department of any government, and you're looking at software that is terrible not because nobody knows how to build better software, but because the people who need it can't afford to pay for better at current prices. Then think about all the things software hasn't touched at all, which is most things. Every small business runs on a spreadsheet and a group chat and a person who remembers stuff.

That means there isn’t now and isn’t going to be a glut of software developers, and anything that looks like one right now is a temporary transitional state. The demand for software, at least inside my 10 year horizon, is for practical purposes infinite, or software developers wouldn’t be as highly paid as they are.

But the job of a “programmer” is about to get very, very different. So different that you might not even recognize it as “programming” any more, while still being recognizably “software development”.

## The job of making software will become what the agents can’t do

If agents are going to eat the entire software development life cycle, what does that leave behind?

To figure that out, I broke the cost of making software into as many component pieces as I could think of. I came up with a long list, in four categories:

Collapsed:

- **Actually writing code**: historically the most expensive part of the whole process, because getting it right was really tricky. The entire industry oriented itself around very expensive programmers as the center of gravity, with every other job more or less orbiting around them. The cost of this, with LLMs, has already collapsed.

Going soon:

- **Reviewing code**: I’ve written about the[death of the code review](https://www.linkedin.com/pulse/when-code-costs-nothing-produce-how-do-you-review-all-laurie-voss-p2jkc/?trackingId=I0w9CTAITXu0FNizYYsnWA%3D%3D)before, the TLDR being: it hasn’t happened yet, but it looks like it’s about to.
- **Maintaining code**: finding bugs, fixing bugs, refactoring. Agents are making real progress here but are still not great.

Next on the chopping block:

- **Shipping code to production**: getting it out of dev onto real production hardware. With various platforms this has been dropping for a while, and my assumption is that agents are about to get very good at it.
- **Scaling up**: not something I’ve seen anyone talk about, this is a big part of successful software development. I’ve not seen people throwing agents at production bottlenecks so far.

Possibly safe:

- **Deciding what to build in the first place**: figuring out what the customer actually wants is a huge part of software development, and so far I haven’t seen anyone throw an agent at it. To my mind, this is the most durable part of the job.
- **Deciding the definition of “good”**: this is the intersection with my day job in the world of AI evaluation. I’ve not seen any attempts to automate this. How would you even know, short of asking a human, what good looks like?
- **Making it delightful**: we can all tell the difference between a piece of software that gets the job done and one that’s actually easy and fun to use. Can an agent? The current state of agentic design does not suggest that they can, but this one is the most wobbly of the three.

Then there’s a bunch of things that are arguably not software development at all, but are still part of the software industry: marketing, user acquisition, retention, branding. Who knows what agents can do with them, but I’m not considering them.

## All juniors did was write the code you told them to, and that’s gone

I already talked about this in [my post about the labor market](https://seldo.com/posts/ai-has-torched-the-market-for-junior-programmers/), so I won’t reiterate the whole argument. The thing agents got good at first was producing code from a description, which is exactly the thing junior developers were hired to do. It was the whole point of hiring a junior: you gave them a well-specified ticket, they produced mediocre code, a senior reviewed it, and over about a decade of that they absorbed enough judgment to become the senior.

The problem from that post is: if you don’t need juniors to handle well-specified tickets any more, where do the seniors come from? We have to train them in a different kind of job. The point of this post is: what job?

Since July the Stanford team has [updated their numbers](https://digitaleconomy.stanford.edu/news/canariesaug26/) and things did not improve for junior developers. The employment gap for 22-to-25-year-olds in AI-exposed jobs is now 19% below where it would be if they'd tracked their less exposed peers, up from 15% a year ago, and it's happening through reduced hiring rather than layoffs. More interesting is *where* it's happening: young workers lost ground in occupations built on knowledge that's been written down somewhere, and experienced workers gained ground in occupations built on knowledge you get by doing the job. The Stanford authors call these codified and tacit knowledge, and I'd call them "stuff that's in the training data" and "stuff that isn't", but it's the same distinction, and it maps exactly onto "what juniors do" and "what seniors do." SignalFire's [2026 talent report](https://www.signalfire.com/blog/signalfire-state-of-talent-report-2026) has the corporate side: entry-level hiring at the big tech companies is down 65% since 2019, at early-stage startups it's down 75%, and yet engineering as a share of hiring went *up*, from 46% to 55%.

Companies are hiring fewer people overall, but a bigger share of the people they do hire are engineers, just not the kind whose primary job is typing code.

## Going soon: reviewing and maintenance

For reviewing and maintenance, agents are clearly not there yet, but the data shows them on an upward trajectory.

On benchmarks where agents fix real bugs in real repositories, frontier models went from roughly 50% to roughly 95% in the last two years, to the point where the main benchmark is [effectively saturated](https://www.morphllm.com/swe-bench-pro) and people have had to build harder ones. On the harder ones, which resist the models having seen the answers during training, the best models now score around 59%. That’s not good enough, but neither was 50% two years ago and that went away really quickly.

A [study of 567 pull requests](https://arxiv.org/pdf/2509.14745) opened by Claude Code across 157 open source projects found 84% of them eventually got merged, a bit below the human rate of 91%, and just over half went in without a human touching them. Google's Big Sleep agent [found a memory corruption bug in SQLite](https://blog.google/innovation-and-ai/technology/safety-security/cybersecurity-updates-summer-2025/) that traditional fuzzers had missed and that attackers already knew about, and has found around twenty more since in things like FFmpeg and ImageMagick.

Until they do, the ability to create code but not to review it is causing an enormous amount of pain. GitHub added [36 million developers and a quarter more commits](https://github.blog/news-insights/octoverse/octoverse-a-new-developer-joins-github-every-second-as-ai-leads-typescript-to-1/) in a year, and the number of merged pull requests on the platform is up something like three and a half times since 2023, with one estimate having agents alone opening 17 million PRs a month. Something should review all of that, but [one study of 33,000 agent PRs](https://arxiv.org/abs/2605.02273) found that most PRs on GitHub, human or agent, get no recorded review at all, and when agent PRs are reviewed, 58% of the time the only reviewer is another agent. In open source, examples abound of projects shutting out new submissions because of a tide of AI slop and the inability to effectively review them; [curl shut down its bug bounty](https://www.bleepingcomputer.com/news/security/curl-ending-bug-bounty-program-after-flood-of-ai-slop-reports/) in January after the share of submitted reports that were real bugs fell from better than 15% to under 5%.

## Next on the chopping block: operations and scaling

For this part of my argument data was really thin on the ground, so I’m relying heavily on my “looks like it’s going to happen” assumption from the start. There are some benchmarks that look more like operating a system than fixing a bug, and agents are [somewhere under 65%](https://artificialanalysis.ai/evaluations/terminalbench-v2-1) on them. This isn’t a thing happening yet, which is why there’s almost no data either way. It’s just the thing that, logically, looks like it’s next.

## What's left is finding out what people actually want, and only they know

So if the code is free and the operations are free, what’s left? It’s sometimes called "product sense", and it’s highly valued in senior developers, but what does that mean exactly?

At some point every piece of software is a formalization of a human desire. Somebody wanted something, and the software is a precise enough statement of that want that a computer can act on it. When a customer says "I need to keep track of my orders," there are ten thousand pieces of software that fit that sentence, and only one of them is right for a bakery, and it's a different one from the one that's right for a car parts factory, and the only person on earth who knows that the customer is running a bakery and not a parts manufacturer is the customer.

You cannot do product discovery mechanically short of reading people’s thoughts. You can't train it into a model, because it isn't in the training data, because it's in the head of one specific baker who's never written it down and wouldn't know how to if you asked them. Somebody has to go and get it out of her, and then turn it into something exact enough to build, and then check that what got built is actually what she meant, which it never is the first time.

## There is no economy of scale in product decisions

The cost of deciding what the customer wants has a very important property: it doesn't transfer well. The definition of "good" for a calendar app and the definition of "good" for a scheduling app, which are two ways of solving roughly the same problem, have almost nothing in common, and two bakeries don't have exactly the same problem either. Whenever you see software with a zillion configuration options that still doesn’t do what you need it to do, you’re feeling this problem. It’s why software so often sucks, and why I say the demand for good software goes to infinity. **Software requirements are more different than we’ve been able to admit** while we’re still trying to write one-size-fits-all software.

As the cost of software creation falls to zero, the bottleneck moves to the description of the problem, and my thesis is that’s where it’s going to stay.

## What about design?

I'd separate out design from this, because it's related but it's not the same thing. Design is the part where two solutions both correctly solve the problem and one of them is the one people actually like using. Everybody who's watched a well-specified product lose to a nicer one knows this is real, and I can't quantify it, and I'm suspicious of anyone who says they can. But I'll note that it has the same structure as the description cost: it's per product, it doesn't transfer, and cheap code makes it more important because when everyone can build the correct thing, the nice thing is what's left to compete on.

## The job that remains is called Product Engineering

So what does that leave behind? Let’s talk history for a little bit.

When computers were new and programmers were scarce and expensive, companies hired a person whose entire job was to sit between the business and the programmers, understand what the business needed, and write it down precisely enough that a programmer could build it without talking to anyone. This person was called a systems analyst. There's [a 1963 memo](https://miamioh.edu/cec/news/2017/08/systems-analysis-history.html) from Miami University describing systems analysis as a brand new profession born out of the mountain of paperwork business executives faced: it was the translation layer, created because the people who could type were too valuable to also do the talking (and also, people who were very good at laying down code seemed to be not very good at talking to humans anyway).

Then software went commercial and, especially, consumer-facing, and the translation job changed shape. Consumers don't want to sit in requirements meetings: they just want to be handed a thing they like. So the person whose job was understanding what people wanted stopped being an analyst who interviewed the business and became a product manager who studied the market, a role [borrowed more or less directly](https://cacm.acm.org/practice/evolution-of-the-product-manager/) from Procter & Gamble's brand managers by way of Intuit and then Microsoft, where a programmer named Jabe Blumenthal invented "program manager" in the late 1980s because Excel for the Mac needed somebody to own what it should do.

The function moved into Product, and Product got separated from engineering as a career, and for the last twenty-five years we've had two professions where there used to be one and a half. I bring this up because it means the job I'm describing isn't a speculative new thing that we'd have to invent. It's a thing we've had for sixty years under two names. My speculation is that it’s about to collapse back into one job.

## The new job is already being hired for, under a dozen names

You can see the start of this change arriving now: it’s showing up as job postings for a role nobody had heard of three years ago.

Palantir coined "forward deployed engineer" for a person who goes and sits with the customer, figures out what they actually need, and builds it, inside the customer's environment, with the customer watching. It was a Palantir oddity. Then in 2025 postings for it [grew by something like eight hundred percent](https://www.paraform.com/blog/forward-deployed-engineer-demand-quadrupled) in nine months, and by this month [a census](https://joinplank.com/fde-job-market) counted almost a thousand live postings across 462 companies, including OpenAI, Anthropic, Databricks, Stripe and Google Cloud, with Salesforce saying it wants a thousand of them to roll out its agent products. The average total comp is around $240,000 and senior ones clear $600,000, which is to say it pays like a senior engineer, because it is one. The same role is being posted as solutions engineer, deployment engineer, applied AI engineer, implementation engineer, and half a dozen other things, because nobody has agreed on the name yet, because it’s so new that nobody has standardized it yet.

But read the job descriptions and you see, roughly, a senior product engineer. The responsibilities include: scope the problem with the customer, understand their business, write production code into systems you didn't build, iterate with them until it works. The code-writing is in there, but it's the smallest part, and it's the part the agent does; what the company is paying $240,000 for is the person who can walk into a car parts factory and come out with a correct definition of "good." **The market has already decided this job is incredibly valuable.**

## But that’s not programming!

Here’s the part that’s going to suck for a lot of people who develop software currently: no, this isn’t programming. It’s recognizably still software development, but laying down code is a vanishingly small part of it and, if the trends I’ve laid out here are real, going to get even smaller.

I want to be careful here because “figure out what to build, not how to build it” is also a description of the part of software development I personally always liked, and there's a well-known failure mode where everyone with an opinion about AI concludes that all jobs will be automated except theirs, which is mysteriously impossible to automate. So take this with the appropriate salt: I think the durable, paid part of making software becomes the part where you understand a problem better than the customer does and think harder about the solution than they can, and I think that's durable because it can't be extracted from the customer mechanically, and I think it's paid because if you don’t do it you get software that everyone agrees sucks, which is to say: most current software.

## The market wants context and taste and nobody is being trained for those

Here's where my forecast runs into a problem.

**The input the software development industry is about to need in unlimited quantities is people who can extract requirements from humans, define good, and exercise taste, and we do not make those people.** Product people fall into their jobs by accident, as a byproduct of the typing job, or sometimes a marketing job, or maybe a consulting job. For developers, you hired a junior to write code, a senior reviewed it, and over a decade the junior picked up judgment by osmosis. That's how every senior engineer I know got their taste, and it's the loop I said in July is now broken, and it's broken because the first rung on the ladder was "type code somebody else reviews" and the agents are going to do both of those things.

Formalized training of product people barely exists. Google's APM program, which [Marissa Mayer started in 2002](https://www.svpg.com/apm-programs/) and which is the template everyone copies, takes about fifty people a year out of something like twelve thousand applicants. Meta, Uber, LinkedIn, Salesforce and a few others run equivalents of similar size. Add them all up and you get maybe a few hundred people a year trained, on purpose, to do the thing I'm claiming is about to be the whole job, against a junior developer pipeline that used to be tens of thousands and is now on fire. Universities teach data structures. Bootcamps teach React. Nobody teaches "go sit with a baker for a week and come back with a spec," and the pipeline for turning junior devs into that role by accident has been closed, also by accident.

The market wants people with context and taste and we are simply not training those. We’re not even sure we know how. Until that changes, the scarce input stays scarce, the people who have it get more expensive, and most of the world’s software stays bad for longer than it needs to.

I do think the market will probably solve for this. The price of the scarce thing goes up until somebody finds it worthwhile to make more of it. IBM is already redesigning its entry-level role around customer contact and specification instead of typing. Companies paying $240,000 for forward deployed engineers will eventually notice it's cheaper to grow them, and universities will eventually notice that "requirements analysis" is a course people would pay for, but it will all happen too slowly, and a cohort of people will get hurt in the meantime, and I'll come back to them. But the demand is real and the demand is what fixes it – eventually.

## The craft as paid work is mostly dead, and that is a real loss

I’ve [posted this sentiment before](https://bsky.app/profile/seldo.com/post/3mh2qbvtxqc22), but it’s a real tragedy that shouldn’t be glossed over. I've seen a lot of despair from career programmers over the last two years and I don't think the right response to it is a chart showing that aggregate employment is going to be fine.

A lot of people got into programming because they love the craft of it. The feeling of a clean abstraction. The satisfaction of a hard bug finally yielding. The specific pleasure of making a machine do exactly what you told it, which is a pleasure most jobs don't offer. Those people did not sign up to interview bakers. Some of them have no interest in product management and some of them are actively bad at it, in the way that some brilliant engineers are, and they're looking at the forecast I've just written and seeing their job turn into a job they'd never have chosen.

I think they're right, and I don't have a consolation prize. The craft of writing code as a thing somebody pays you to do is, I think, mostly over, outside of niches that will get narrower every year. That's a real loss and it's a loss for the profession as well as for the people, because the craft is where a lot of the taste I've been talking about actually came from, and we're about to find out what taste looks like when nobody grew up doing the thing.

Two things I'd say that aren't consolation, just observations. One is that for a fair number of the people who think they loved the typing, the part they actually loved was the moment before the typing, when a vague mess of a problem resolved into a precise shape in their head. That moment is the job now. If that's what you loved, you're going to be fine and possibly better than fine, because the industry is about to be desperate for you. The other is that the craft survives, the way woodworking survived the furniture factory, as a thing people do because they love it and occasionally get paid a premium for. Developers write software the way singers sing. That was true when it was free and it'll be true when it's automated, and the people who love it will keep doing it, and some of the best software will keep coming from them. It just won't be the job.

## Ten years of turmoil lie ahead

It’s been a long 4000 words, so let’s review.

The cost of writing code collapsed, and the cost of reviewing, fixing and operating it is following, and I'm assuming it gets there. What's left of making software is finding out what people actually want, defining it precisely, and making it pleasant to use. That cost is per piece of software and doesn't transfer, so as the amount of software goes to infinity, which it will because there's no ceiling on demand, that cost becomes the whole job.

That job is called a product engineer. It's being hired for right now under a dozen new names at senior engineer pay. And the training pipeline for it is roughly fifty people a year at Google, because the way we used to produce it was as a side effect of a typing job that no longer exists.

I think the next ten years are going to be ugly, because the load is arriving before the tools do, the junior ladder is gone before the replacement exists, and a lot of people who loved the craft are going to have to decide whether they love the job that's replacing it. I think by ten years it shakes out, the way it did when compilers and then frameworks and then open source each made a generation’s worth of typing unnecessary, into a profession that is larger than today's, pays about as well, and is mostly shaped like product engineering. At twenty years I have no idea; if we hit anything resembling general intelligence in that window then this post and every other post about jobs is moot. But for the horizon I can see, the forecast is: more software, more people making it, and almost none of them typing. **We are all product engineers now, whether we like it or not, and a lot of us won't.**
