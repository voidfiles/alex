# The end of programming — Paul Dix

# The end of programming

Last week Bun 1.4 was released. This was the one that contains the rewrite of Bun from Zig into Rust, apparently containing more than 1 millions new lines of Rust code. And while this caused a bunch of drama in the programming community centered around the language switch, I think the most important thing about this release is how the rewrite was done and the scale of it. The details of this, along with my own experiences, and soon to arrive advances in AI lead me to believe that we’ve arrived at the end of programming as we know it.

What I mean by this is that I think the act of writing code manually and having other humans review it to create useful, working software is headed for extinction. Or at the very least, it will be drowned out by the absolute deluge of useful, working software that will be created by agents, with humans reviewing only the end result, not the code itself. We’ll have more software than we’ve ever had, but most of the code for it won’t have been written or even read by humans.

To be sure, there will also be a mountain of slop. Of buggy, useless, terrible, offensive software that conforms to no programmer’s sense of aesthetic or purpose and style. But there will also be well engineered, working software that solves real problems, yet hasn’t been reviewed in fine detail by human eyes.

This explosion in software can already be seen in this graph from [GitHub’s post about their August 17th outage](https://github.blog/news-insights/company-news/the-august-17-outage-and-the-work-ahead/):

Since last year there’s a steep exponential climb in the amount of code being produced. My theory is that most of this is actually from side projects or projects internal to companies that are skunk works, or for individual users. Things that are viewed as non-critical. In most companies, there is still significant organizational friction to individual developers shipping 2x more when it comes to the products that drive the business, let alone 10x or 100x.

Almost all of the code in those graphs was produced by models that are currently not at the frontier. It was produced by the frontier models of months ago, which is to say, not Fable 5 and not GPT 5.6 Sol.

## Anthropic and OpenAI developers live in the near future

Reading the [details of the Bun Rust rewrite](https://bun.com/blog/bun-in-rust), the big highlights are that it was driven by one developer, Jarred Sumner, working with a pre-release version of Fable 5 and a seemingly unlimited token budget. He created the working harness and framework for agents to work in parallel and translate the Zig code base into Rust.

Over the course of 11 days, multiple agents produced 6,778 commits and burned through enough tokens that it would have cost roughly $165,000 in API pricing.

I remember when the drama around this rewrite first sprung up in early May, well before the above blog post was written. It was revealed only through [a merge of the rewrite](https://github.com/oven-sh/bun/pull/30412), which showed +1,009,257 -4,024 in changes. I was amazed at the scale and theorized that they had achieved this with Mythos:

> Also, I’m dying to know if this was done with unlimited Mythos tokens. Is this the near future for the rest of us? Or the now and they did it with Opus 4.7 tokens? My guess is the former. So it’s a preview of what’s possible later this year.

My experience at that time was that I didn’t think such a thing was possible with Opus 4.7 so it must have been the yet to be released Mythos that enabled a rewrite like this that actually worked.

The fact that AI wrote 1M LOC and then refined it over the course of the next couple of months to produce a reliable piece of software that is currently running on millions of developer machines is absolutely mind blowing. And you can say, “well it’s not that impressive because they had an oracle to compare against, so it was simple to go from one language to another”, but I think that’s selling this entire thing short. If you can build a verification system and give proper direction, AI can produce a highly complex, highly sophisticated piece of software and it can continue to refine it until it just works.

If you pay attention to what Anthropic and OpenAI developers have been saying on X in the last couple of months, they each ship dozens or hundreds of PRs per week and they have shifted their focus higher up the stack. This makes sense as it’s not really possible for a developer to closely review hundreds of PRs worth of code every week while also producing their own work.

If you take what they say publicly at face value, they are no longer doing very close review of every line of code that gets shipped. They are spending their time building systems, prompts and verification tooling to get AIs to produce their software at scale and with high velocity. At least that’s what I’m interpreting when they talk about loops.

Yet they are operating in a world where they have unlimited Fable and Astra (OpenAI’s next model) access. They live in a near-term future that we peasants will likely experience a year from now. Their experience of using AI to develop software is not the experience of the rest of us on the field waiting for our weekly Fable allotment to reset.

The Bun 1.4 release should give you a glimpse of what’s possible if you pair Fable level intelligence with near unlimited tokens. Software delivery at scale, that works, as proven on millions of working deployments.

## My experience report from the field

I have two recent anecdotes to report from my own experience. My vibes feeling is that Fable is qualitatively different than previous models in similar way to how people noticed Opus 4.5 released at the end of last November was different. It has crossed a threshold where more can be produced with higher level direction and less supervision. I’m able to give it requirements, architecture and instructions for a feature I want to develop and it is able to create a fully functioning first version over multiple working hours with no further interaction from me.

My two examples are both things that haven’t shipped in InfluxDB, but they’re new capabilities I had built in a fork. I chose these to see what was possible with the new model.

The first is Iceberg integration, making data in InfluxDB accessible through Iceberg REST, or on an external S3 bucket and Glue catalog. This is a complex feature requiring:

- API & CLI to enable the feature
- Implementation of the Iceberg REST API
- Deep ties to the compactor to create the Iceberg manifests and Parquet data in the external store
- Creation of Iceberg manifests or requests out to Glue
- S3 API implemented in InfluxDB for non-export use cases

This is thousands of lines of implementation and test code. I hashed out the rough architecture design and requirements and then directed Fable to do the work through sub-agents, triggering code reviews, and supervising the process. 14 hours later, it had produced a working version. I then told it to verify everything end-to-end with a running InfluxDB cluster and using DuckDB and PyIceberg as the external clients. It fixed a few bugs and verified it all worked.

The second example is the creation of an edge data replication system for InfluxDB. This is multiple individual InfluxDB nodes running as satellites that periodically replicate compressed data up to a central InfluxDB cluster. It defines:

- API to set what will get replicated and on what frequency
- CLI to access above
- Updates to the compactor, which is used to filter, aggregate and create compressed data to replicate, along with the tracking to know what has gone up and what remains
- API for the edge node to access catalog information to be used in the replication payload
- API for receiving compressed blocks of data into the pipeline
- Metrics and system tables to enable visibility of all of the entire setup

I laid out the architecture and gave examples of what the user experience should look like. I collaborated with Fable to produce a design, then told it to do the work, acting as a supervisor. 28 hours later, it had a mostly functioning implementation.

I then directed it to deploy it inside our test infrastructure in AWS and observe the metrics and logs and fix bugs as it went. After a few short iterations it got to an end-to-end working implementation, which is still running a few months later. I even later had it build a UI that shows the replication action across nodes with rates of data transfer, just because, why not.

Of course, neither of these things is currently shipped, or supported and isn’t what I’d call production ready software. So you could say what many say about AI, which is that it helps you ship the prototype faster. But that isn’t really giving enough credit here.

The prototype is working software. And the improvement and testing of that prototype is further enabled by more improvement loops with the AI. It gets better with more testing and verification, not through human code review, but through usage and testing.

I did each these with a weekly Fable allotment and my subscription (had to wait a week between). What I haven’t been able to do is to put this in the cloud, on an improvement loop with unlimited Fable credits. We can’t afford the hundreds of thousands of dollars of monthly spend that I’d likely rack up if sent the top frontier agent off to do my bidding 24/7.

Jarred produced the Rust rewrite in 11 days, but then had agents working on continuous improvement for months before releasing it as an official supported release. The prototype is the beginning, but the agent will also help you ship the iterated, improved, and hardened production ready product.

## The near future for us programming peasants

At this time last year we had Opus 4.1 and GPT-5. You can now buy better intelligence at a fraction of the price. We got Opus 4.5 and GPT 5.2 in late November and early December last year. These are the two models that caused every CTO to freak out over their winter break about how it was possible to just create features and software at will.

I expect that we’ll have another one or two big releases from OpenAI and Anthropic this year. My best guess is that we get Astra from OpenAI sometime in September and it will be Mythos/Fable class and likely more capable than Fable 5.

I expect the Fable & Astra equivalents of the threshold crossing Opus 4.5 and GPT 5.2 releases either by the end of this year or early next.

That level of model intelligence and capability will be able to create any feature you can think of for your software. And it will work. And it can test and verify it for you. It will do it as quickly as you’re willing to take delivery of the code. The only question will be what do you want to ship? And what do you want to support?

By the end of next year, this level of intelligence will be cheap enough that most of us will be able to work with it full time, like Jarred was able to work with pre-release Fable to produce Bun 1.4.

In another year or two, we’ll get broad access to systems that can produce tokens at 10x to 100x the speed at a fraction of the cost. See the [Cerebras C4 announcement](https://www.cerebras.ai/cs4) and [OpenAI Jalapeño results](https://x.com/firstadopter/status/2092266927377039838). Broader, cheaper access to frontier intelligence at incredible speeds is coming.

Organizational inertia will likely mean that there’s another decade of humans writing code by hand and having their colleagues review every line of it. Many, if not most, companies will continue to develop software as they have before.

But the most productive software creators will be doing it without programming in any traditional sense. They’ll be directing AIs, creating harnesses, and software factories, and QA and verification systems that ship working software faster than we’ve ever seen before.

And we will have arrived at the point where we have more running, production software written by AIs than written by humans. It’ll be the end of programming.
