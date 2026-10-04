# The Shifting Dynamics & Meta-Moats of AI - Michael Dempsey: Blog

> *Perhaps the best targets for computer scientists and engineers looking to build new systems is not to find intelligences that humans lack. Instead, it is to identify the skills that generate outsized income and build machines that allow many more people to benefit from those skills.*
>
> *[The Turing Transformation](https://www.brookings.edu/articles/the-turing-transformation-artificial-intelligence-intelligence-augmentation-and-skill-premiums/)*

Since over 8 years ago when we started investing in AI at [Compound](http://compound.vc) we have held fairly constant (albeit increasingly data-informed and nuanced) investment views. These views encapsulate everything from timelines surrounding technology, to the optimal types of startups that certain types of founders should start within AI, to where value will accrue amongst companies, to inflection points of the industry, to areas most ripe (and under-appreciated) for disruption or enablement, and more.

This could partially be summarized in the simplistic framing below from 2017 and has been published many times in our annual letters over the years ([2018](https://compoundvc.medium.com/compound-annual-letter-2018-61f34e462745), [2019](https://compoundvc.medium.com/compound-2019-annual-letter-e42c5aad6a41), [2022](https://compoundvc.medium.com/compound-2022-annual-letter-30f8914cf67e)):

![](https://www.michaeldempsey.me/blog/wp-content/uploads/2024/04/Screenshot-2024-04-16-at-1.47.46 PM.png)

Compound’s simplified AI framework in 2017 from our annual LP meeting

Despite this high-level framing, our conviction was perhaps less deep then on the multi-variable dynamics that founders needed to navigate while company building in AI. This was largely because all of AI felt quite novel, with few consensus winners for years, as no company in the industry had meaningfully commercially inflected. There were very few “best practices” or “table stakes” operating principles.[1](javascript:void(0))As with all things, this in some ways, will always be true, and all great companies will also always be n of 1

AI technical approaches (and perhaps the entire industry) have become increasingly consensus with Transformers leading the way and a variety of iterations getting coalesced around quite quickly within the community over time (CoT, RAG, MoE, Model Merging, etc.). [2](javascript:void(0))We can argue whether this is good or bad

There are of course emerging developments via new approaches like RWKV, SSMs, and more, however it feels more likely this will be done via skunkworks team in large orgs or via newer orgs aimed at disruption, while the consensus premise of performance at incumbents (and most AI Labs founded in the past 3 years) will be based on compute, data, and scale.[3](javascript:void(0))I highly recommend [reading our piece on alternatives to Transformers](https://www.mackenziemorehead.com/is-attention-all-you-need/).

This monotony naturally happens in industries that have fairly monolithic leaders and also experience large inflows of talent that are looking to be “shown the way” as they acclimate to a new category or industry.

With this inflection of commercial and technical success, we have new learnings surrounding company and moat building in AI in 2024 and onward.

## On Speed

For better or for worse, every single company will face material competition in AI over the next few years either directly or [via death by a thousand cuts](https://mhdempsey.substack.com/p/the-most-dangerous-thing-about-the). There will be areas that attract tons of short-term capital, [open source projects](https://github.com/princeton-nlp/SWE-agent) that attempt to cut away at [closed-source competitors](https://www.cognition-labs.com/), and products/companies that over-promise and under-deliver, but still create a large amount of noise. Thus, in the short term, a main goal for a startup is to continue to stand out amongst this noise.

> …in reality AI companies are perhaps some of the most complex businesses we’ve had being built in tech in some time. Doing core AI model R&D necessitates a need to play 4D Chess around research communities, capital accumulation and deployment, talent acquisition, competitive understanding, and commercialization.
> Michael Dempsey <https://www.michaeldempsey.me/blog/2023/07/18/the-dark-forest-of-rd-and-capital-deployment-in-ai/>

Due to the complexity of AI companies and the category at large, the nuances of building moats gets split across short, mid, and long-term dynamics.

Once a startup is able to create enough early moats, they then move into the necessity to continue to maintain velocity over multiple years. Again, capital will continue to flow into the space creating competition across multiple vectors for your business for longer than many appreciate, and as model performance commoditizes, incumbents will also begin to be late movers in some areas.[4](javascript:void(0))This is why I’ve written so much about [brand moats](https://www.michaeldempsey.me/blog/2023/10/03/open-source-ai-business-models-brand-moats/) in the past and the importance of them.

Effectively what this means is that founders have to do all of the things great companies do in software, but faster than everyone else, in a space that is moving with uncertain progress and speed. And they have to do it a very high level, potentially implementing or in some cases creating things that have never been created before.

The industry at large seems to have noticed this, however few companies are able to execute at the rate that outpaces natural industry wide compression and erosion of advantages, often leading to a ton of companies with similar goals competing on the same, eventually inconsequential axis of competition.[5](javascript:void(0))An example of this is likely photorealism on the generation side over the next 1-3 years. This is why being opinionated on product will matter more and more.

In some ways, OpenAI is the company which fired the starting gun and is a good example of the speed dynamic.

After the ChatGPT experiment was such a success (supposedly undertaken as an attempt to front-run competitors) a small team at OpenAI quickly became a much larger team, as the company saw the necessity to move into a faster shipping product org with tighter feedback loops after being a slow-moving research org for many years once the proverbial chasm was crossed with transformers and GPT-2.[6](javascript:void(0))I’m using the term “slow” relatively here, chill We’ll come back to this.

Other orgs like [Runway](http://runwayml.com) (a [Compound portfolio company](https://notes.michaeldempsey.me/post/637778886529253376/runway)) and [Perplexity](http://perplexity.ai) are great examples of organizations with elite speed at their core. Both companies rose from seemingly nowhere to those not paying attention closely, shipping a wide range of features, and shifting narratives from utilizing open-sourced models or APIs into proprietary ones as their product feature sets deepened with great velocity.

Maintaining this velocity doesn’t just mean founders must do it over 12 to 24 months, before “growing up” into larger organizations and asymptoting. Instead in AI, the best companies will have to both be elite sprinters while also being the fastest marathon runner. [7](javascript:void(0))Sounds fair right?

Naturally, the prize at the end of the race will be immensely valuable, but this can go wrong in many different ways, with the ability to get distracted fighting the wrong battles always being a constant.

If i had to guess, this is where we will see a majority of companies fail; taking advantage of false signs of early *durable* PMF, spinning wheels playing short-term games, only to get leapfrogged or destroyed by other startups or companies playing long-term games (again, 4D chess).

The most common state of this is building a product that creates incremental value on top short-term base model performance, instead of leveraging increases in base model performance to increase product value materially.

Sam Altman framed a way to understand this with a simple heuristic [recently in an interview](https://www.youtube.com/watch?v=G8T1O81W96Y&ab_channel=20VCwithHarryStebbings):

“*When we just do our fundamental job, which is make the model and its tooling better with every crank, then you get the ‘OpenAI killed my startup’ meme. If you’re building something on GPT-4 that a reasonable observer would say ‘if GPT-5 is as much better as GPT-4 over GPT-3 was.’..not because we don’t like you but just because we like have a mission…we’re going to steamroll you.”*

While Brad Lightcap said to *“Ask the company whether a 100x Improvement in the model is something they’re excited about.”* in the same interview.

Another fail state of short-term games are those building products with a skeuomorphic framing of building something that is “x but with AI” instead building a novel thing that is “y” because of AI.

Because of these potentially destructive distractions (along with many others not discussed here), we believe founders need to build structures that enable their team to fight against this pitfall from a cultural perspective and a shipping and executional perspective.

In addition, they must build infrastructure that enables them to not be rate-limited in areas like compute, data, and talent, all enabled by capital that allows them to not have to throttle down speed of product iteration and possibly be disrupted due to the lack of fully unassailable moats that exist within AI currently.

Put simplistically, building an AI company is *not* just about survival.

## Data Flywheels

![](https://www.michaeldempsey.me/blog/wp-content/uploads/2024/04/dataflywheelchem-1024x334.png)

[Scaling deep learning for materials discovery](https://www.nature.com/articles/s41586-023-06735-9)

Multimodality and scaling has taught us that a large amount of ROI from AI can come from “connecting the dots” of existing data today. The early canonical example of this in LLMs has been when models are taught coding tasks and it improves performance across a variety of seemingly unrelated tasks. We now have seen similar dynamics across multimodality as companies push from LLMs or “Multimodal models” to World Models in order to increase performance and world understanding brought on by image, audio, video, and more.

Pairing this with the [continual obliteration of context windows](https://twitter.com/mackenziejem/status/1780203651157410227), what this means is that perhaps pre-training a large model and then fine tuning it with data is not the short to mid-term moat that people once believed.

That said, LLMs have not materially shown intelligence outside of training data distribution and across a variety of non-language-only tasks we have seen that data and scale are not nearly maximized in order to drive performance like we have for more traditional natural language understanding enabled early on by things like [The Pile](https://pile.eleuther.ai/) and more.

This has caused us to progressively prefer companies that aim to own more of the stack than originally anticipated, including [owning the entire stack and building an AI-enabled operating company](https://mhdempsey.substack.com/p/full-stack-deep-tech-startups-and).[8](javascript:void(0))[AIFleet](http://aifleet.com) in our portfolio is an example of this

Companies that are in industries where data is structurally locked within incumbents with little computational excellence (healthcare, bio, industrials) are also increasingly attractive if you are able to navigate partnerships and more.

These dynamics allow a subset of companies to gather unique large scale data for a variety of tasks, and/or build custom workflows that allow their business to generate novel datasets[9](javascript:void(0))I briefly touched on this dynamic [in this post](https://www.michaeldempsey.me/blog/2023/07/18/the-dark-forest-of-rd-and-capital-deployment-in-ai/) and most importantly **close the loop** with real world proof and feedback, bridging a new form of [Sim2Real](https://medium.com/@sim30217/sim2real-fa835321342a#:~:text=Sim2Real%2C%20short%20for%20%E2%80%9Csimulation%20to,environment%20to%20real%2Dworld%20applications.) Gap perhaps best framed as the *Bits To Atoms Gap*.

### Synthetic Data

> *…then we can take another step back. With enough specific modules and dynamic beings in a simulated environment, we can better understand how all types of robots (cars, delivery robots, social robots, etc.) will interact autonomously with our real (and digital) world.*
>
> [How to drive 10 billion miles in an autonomous vehicle](https://medium.com/@mhdempsey/how-to-drive-10-billion-miles-in-an-autonomous-vehicle-7c9b81c1ddac), 2017

Across all times in AI there is an ever-presence of the promise of synthetic data, and just like any other AI hype cycle, it increasingly feels important to have a view of how that may play a role in a given sector and company progressing towards superutility.

![](https://www.michaeldempsey.me/blog/wp-content/uploads/2024/04/syndata1.png)

[Machine Learning for Synthetic Data Generation: A Review](https://arxiv.org/html/2302.04062v6)

While we [initially were turned onto these use-cases as it related to AVs back in 2016](https://twitter.com/mhdempsey/status/869938931713937409), the world seems more convinced than ever of the importance of synthetic data for AGI, ASI, or whatever next order meaningful inflections of performance we see across embodied and non-embodied intelligence. Because of this, again, it wouldn’t shock us if across modalities a few different organizations become world class at *generating* their data and use that as a compounding advantage.[10](javascript:void(0))It’s also likely we start to see synthetic data generation companies pop up again, which we have lots of views on [having backed AI Reverie](https://medium.com/@mhdempsey/ai-reverie-f67251b7cf1b) which was acquired by Meta.

For companies that are able to deploy and get user feedback at scale, synthetic data will enable improvement of their models in a more efficient way than gathering loads of varied data quality and tossing it into piles of compute credits only to realize a single digit percent of that data is valuable.

For companies operating in sparse data environments, synthetic data will enable them to reach the point of deployment faster or figure out where to make “collect vs. buy vs. generate” data decisions to once again, have better scale and efficiency faster.

![](https://www.michaeldempsey.me/blog/wp-content/uploads/2024/04/syndata2.png)

[Comprehensive Exploration of Synthetic Data Generation: A Survey](https://arxiv.org/pdf/2401.02524.pdf)[11](javascript:void(0))To be honest this chart is just awesome and it sorta fit here

My hypothesis is that unfortunately this won’t be prioritized in organizations enough in the near-term and by the time it is, it is likely too late. Because of this, our main advice would be for companies to have a consistent hypothesis on the implicit trade-offs they are making on data acquisition and why it is the dominant approach.

## Market Timing & Talent

There is a longer post I’ll write on deep tech talent in 2024 broadly, but many of the sentiments shared in point #3 of my 2020 post on the topic, have loudly echoed in AI land over the past 18 months.

> …As you talk to more veterans in this space, many are pretty disenchanted by their past 7+ years of work. 
>
> Their friends at Uber, AirBnB, and Stripe are multi-millionaires (some on paper), same with their friends at FAMGA, and they possibly are too but don’t really have anything material to point to in the real world.
>
> …I think many are kind of waiting for a “moment” that feels like everything is once again possible. I don’t think those moments are obvious in the present.
>
> Michael Dempsey <https://notes.michaeldempsey.me/post/636878548075937792/the-deep-tech-deficit-why-more-people-arent>

In 2024, you have a growing cohort of researchers that have felt this “moment” and feel the need to deploy to the real world more than ever. This feeling has become especially acute as larger orgs are less interested in sharing research publicly, so the clout associated with great research has diminished and is now tied in some form to products that are shipped.

Alongside of this, there has been a shift of ideal team compositions within AI.

AI has started to pull talent from all over, allowing very talented engineers to figure out how to problem solve with a set of constraints brought on by building in AI. These constraints candidly are familiar to engineers (especially those who have worked at startups) and are somewhat foreign to researchers and engineers from larger megatech labs, thus they are highly complimentary and at times more necessary skillsets to have within AI startups.[12](javascript:void(0))Runway has noticed a form of this and launched the [Runway Acceleration Program](https://research.runwayml.com/acceleration-program) in response.

As technology categories go through waves of a given cycle[13](javascript:void(0))We could argue this is the 2nd or 3rd AI Cycle you start to see a new generation of talent flow dynamics due to learnings from the first major wave of the cycle being exhausted.

This can look like people leaving the incumbents or dominant companies to go gain 0-1 Skillsets after accumulating Scaling Skillsets. It can also look like the talented employees at scaling startups leaving to solve problems they now have acutely felt.

At this stage of the cycle, industries often get heavy infra/dev tooling spin offs as custom-built infra and tooling can be brought outside of organizations to be used by the next wave of startups who don’t have to reinvent the wheel. We saw this as many teams spun out of the AirBnBs, Ubers, and more of the world doing similar data-focused plays a few years ago.

Across a range of conversations, there is a general lack of consensus amongst talent around what companies that own parts of the stack are unassailable versus not in AI, leading to bifurcation of this talent that believes they must work at *either* a Frontier lab (OpenAI, Anthropic, DeepGoog, MSR, MetaAI) or an unexplored category (Foundation Models for Bio being a loud one) versus others that think it all is pointless and the next wave of innovation will come only from what gets built on top of the models.

### **Incremental Spin Outs & Fragmentation of Talent**

At times of peak euphoria in areas that have had long ramp times (all of deep tech), we consistently see a dynamic where many will spin out of the companies that caused the Cambrian Explosions in order to re-invent the wheel marginally better than their former employers/scaling incumbents. We have seen this time and time again and typically these companies mark some strange middle ground timing of technology maturation cycles.

This happened with Autonomous Vehicles amidst a cycle of talent starting from [DARPA’s 2007 Grand Challenge](https://medium.com/@mhdempsey/2007-darpa-grand-challenge-roster-e1d05fccf428) congregating to 510 Systems/Waymo, Tesla, and Cruise and eventually leading to a dispersion of a bunch of other AV companies predicated *on the same technical approaches* of the incumbents. The vast majority of these companies raised easy venture capital and have failed or likely will not reach their promises of outcompeting early innovative “incumbents”.

As an investor, I feel this is a disastrous way to lose money as it is in some way predicated on incrementalism instead of step function changes.

As a founder, I would be very certain what the differentiated hypotheses you are testing are and how you are uniquely suited to capture that value outside of the tech world’s version of [“nobody goes there anymore, it’s too crowded.”](https://quoteinvestigator.com/2014/08/29/too-crowded/) as it relates to your former employer.

In moments where performance is inflecting, people underrate many of the scaled advantages of incumbents, only to learn harsh lessons in the valleys of diminishing returns and distribution.

### The Fallacy of *Soon To Be Solved* & The Value of Contrarian Approaches

Whenever people view currently not solved, very difficult problems as “clearly soon to be solved” problems, we at Compound tend to perk up.

The technology industry has gotten very good at extrapolating progress to its end state, however still is sub-par at projecting time horizons and more importantly, the “random” walks that might get us to these end states.

Scaling laws may be a version of this, and so similar to last year’s view when we said *“While it is currently unclear to us what will change, we have a hard time believing that nothing will.”*, we tend to believe there [could be some large changes lurking](https://www.mackenziemorehead.com/is-attention-all-you-need/) that are unknown, and there could be final mover advantages that we don’t appreciate yet within AI.

We think this could mirror the ways that perhaps the AV world viewed autonomy as a *soon to be solved problem* and thus didn’t appreciate end-to-end approaches that made us listen very closely when we met Alex Kendall at [Wayve](http://wayve.ai), eventually bringing us to co-lead their seed round.

A final point on this is that within deep tech, talent seems to consolidate at a far faster rate than in other areas of technology broadly. As we see AI continue to progress and as we see the nature of how people think about the space continue to bifurcate into camps of “open field” or “already won” we will see talent advantages begin to materially accrue to those that can make credible cases for their camp of thought.

All of this can be perhaps overly simplified another way:

Whether someone intensely covets a job at OpenAI and nowhere else is perhaps a great Rorschach Test for someone’s conviction in their view of the future of AI.

## **An Updated framework**

![](https://www.michaeldempsey.me/blog/wp-content/uploads/2024/04/Frontier-LLMs.png)

Going back to the beginning of this post, one can look at moats in AI as a collection of meta-moats, each of which decay over time at varying levels of industry maturation and company entrenchment/distribution.

In the short-term, the core moats built are quite obvious, all with a goal of gaining early distribution and PMF in an effort to either be first to market in your industry (because all industries right now are seeking AI partnerships/experiments) or to stand out amongst the loud noise.

As these metrics are proven out, companies must figure out where their excellence lies and how they can compound this excellence with capital in order to maintain compute and talent, which feeds into product, research, and further distribution towards scaling PMF.

Over time, startups will come and go, aiming to unseat the leaders either with short-term improvements (*”Hey look at this new model that does this one thing (or eval) better than all the others!”*), different go-to-market motions (service-driven contracts alongside traditional scalable contracts, custom models, etc.), over-engineered demos (rip), highly contrarian or opinionated approaches that causes switching dynamics (some of which may last), and/or an elite ability to lock down partnerships.

In the long-term, these such attacks will be held off by a long-standing brand of maintaining a lead *over time*, material performance edge due to data, and/or product depth that creates high switching costs and enables scaled distribution (both directly and perhaps via previous partnerships) across many different customer types.

This framework has nuances across all areas discussed in this post and more, however in reality it just further illustrates that company building in AI is a marathon of an idea maze predicated on scaled execution against a variety of prizes that for better or for worse, the vast majority of builders in tech are running at today.[14](javascript:void(0))And the vast majority of investors are trying to allocate to.

A framing of looking at this Meta-Moat X Time Horizon chart is to analyze what axis of competition your company is predicated on and how does it accelerate as we progress through AI maturation.

While I’ve laid out a potential bear framing for OpenAI (scale, money, data underpinned by *transformers is all you need*, until you don’t) a perhaps hyper-bullish take is that as an organization they have created the machinery that is best at exploring and scaling model development, and this has bought them time to continue developing into an increasingly competent product organization. All at a time where other companies are *“trying to hit a moving target with a single dart”* as [Kevin Kwok](https://twitter.com/kevinakwok) so brilliantly put it to me.

Put simply, it is existential that startups understand the machine they are building.

*Thanks to [Kevin](https://twitter.com/kevinakwok) for thoughts.*
