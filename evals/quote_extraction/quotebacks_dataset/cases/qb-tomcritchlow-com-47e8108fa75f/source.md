*Everything here is my opinion. I do not speak for your employer.*

## 2021-12-01 [»](https://apenwarr.ca/log/20211201-100-years-of-whatever-this-will-be)

**100 years of whatever this will be**

What if all these weird tech trends actually add up to something?

Last time, we explored why various bits of trendy technology are, in my opinion, simply never going to be able to achieve their goals. But we ended on a hopeful(?) note: maybe that doesn't matter. Maybe the fact that people really, really, really want it, is enough.

Since writing that, I've been thinking about it more.

I think we are all gradually becoming more aware of patterns, of major things wrong with our society. They echo some patterns we've been seeing for decades now. The patterns go far beyond tech, extending into economics and politics and culture. There's a growing feeling of malaise many of us feel:

- Rich, powerful, greedy people and corporations just get richer, more powerful, and more greedy.
- Everyone seems to increasingly be in it for themselves, not for society.
- Or, people who *are*in it for society tend to lose or to get screwed until they give up.
- Artists really *don't*get enough of a reward for all the benefit they provide.
- Big banks and big governments really *do*nonspecifically just suck a lot.
- The gap between the haves and have-nots keeps widening.
- You can't hope to run an Internet service unless you pay out a fraction to one of the Big Cloud Providers, just like you couldn't run software without paying IBM and then Microsoft, back in those days.
- Bloody egress fees, man. What a racket.
- Your phone can run mapreduce jobs 10x-100x faster than your timeshared cloud instance that costs more. Plus it has a GPU.
- One SSD in a Macbook is ~1000x faster than the default disk in an EC2 instance.
- Software stacks, governments, and financial systems: they all keep getting more and more bloated and complex while somehow delivering less per dollar, gigahertz, gigabyte, or watt.
- Computers are so hard to run now, that we are supposed to give up and pay a subscription to someone - well, actually to every software microvendor - to do it for us.
- We even pay 30% margins to App Stores mainly so they can *not*let us download apps that are "too dangerous."
- IT security has become literally impossible: if you install all the patches, you get SolarWinds-style supply chain malware delivered to you automatically. If you don't install the patches, well, that's worse. Either way, enjoy your ransomware.
- Software intercompatibility is trending toward zero. Text chat apps are literally the easiest thing in the world to imagine making compatible - they just send very short strings, very rarely, to very small networks of people! But I use at least 7 separate ones because every vendor wants their own stupid castle and won't share. Don't even get me started about books or video.
- The most reasonable daycare and public transit in the Bay Area is available only with your Big Tech Employee ID card.
- Everything about modern business is designed to funnel money, faster and faster, to a few people who have demonstrated they can be productive. This totally works, up to a point. But we've now reached the extreme corner cases of capitalism. Winning money is surely a motivator, but that motivation goes down the more you have. Eventually it simply stops mattering at all. Capitalism has become a "success disaster."

Writing all this down, you know what? I'm kind of mad about it too. Not so mad that I'll go chasing obviously-ill-fated scurrilous rainbow financial instruments. But there's something here that needs solving. If I'm not solving it, or part of it, or at least trying, then I'm... wasting my time. Who cares about money? This is a systemic train wreck, well underway.

We have, in Western society, managed to simultaneously botch the dreams of democracy, capitalism, social coherence, and techno-utopianism, *all at once*. It's embarrassing actually. I am embarrassed. You should be embarrassed.

**"Decentralization"**

I'm a networking person and a systems person, so please forgive me if I talk about all this through my favourite lens. Societies, governments, economies, social networks, and scalable computing all have something in common: **they are all distributed systems.**

And.

And everyone.

*Everyone* seems to have an *increasingly horrifically misguided idea* of how distributed systems work.

There is of course the most obvious horrifically misguided recently-popular "decentralized" system, whose name shall not be spoken in this essay. Instead let's back up to something older and better understood: markets. The fundamental mechanism of the capitalist model.

Markets are great! They work! Centrally planning a whole society clearly does not work (demonstrated, bloodily, several times). Centrally planning corporations seems to work, up to a certain size. Connecting those corporations together using markets is the most efficient option we've found so far.

But there's a catch. People like to use the term *free market* to describe the optimal market system, but that's pretty lousy terminology. The truth is, functioning markets are not "free" at all. They are regulated. Unregulated markets rapidly devolve into monopolies, oligopolies, monopsonies, and, if things get *really* bad, libertarianism. Once you arrive there, every thread ends up with people posting about "a monopoly on the use of force" and "paying taxes at gunpoint" and "I'll run my *own* fire department" and things that "end at the tip of the other person's nose," and all useful discourse terminates forevermore.

The job of market regulation - fundamentally a restriction on your freedom - is to prevent all that bad stuff. Markets work well as long as they're in, as we call it in engineering, the "continuous control region," that is, the part far away from any weird outliers. You need no participant in the market to have too much power. You need downside protection (bankruptcy, social safety net, insurance). You need fair enforcement of contracts (which is different from *literal* enforcement of contracts).

And yet: markets are distributed systems.

Even though there are, in fact, very strict regulators and regulations, I can still enter into a contract with you *without ever telling anyone*. I can buy something from you, in cash, and nobody needs to know. (Tax authorities merely *want* to know, and anyway, notifying them is asynchronous and lossy.) Prices are set through peer-to-peer negotiation and supply and demand, almost automatically, through what some call an "invisible hand." It's really neat.

As long as we're in the continuous control region.

As long as the regulators are doing their job.

Here's what everyone peddling the new trendy systems is so desperately trying to forget, that makes all of them absurdly expensive and destined to fail, even if the things we want from them are beautiful and desirable and well worth working on. Here is the very bad news:

**Regulation is a centralized function.**

The job of regulation is to *stop distributed systems from going awry*.

Because distributed systems *always* go awry.

If you design a distributed control system to stop a distributed system from going awry, it might even work. It'll be unnecessarily expensive and complex, but it might work... until the control system itself, inevitably, goes awry.

I find myself linking to this article way too much lately, but here it is again: [The Tyranny of Structurelessness](https://www.jofreeman.com/joreen/tyranny.htm) by Jo Freeman. You should read it. The summary is that in any system, if you don't have an explicit hierarchy, then you have an implicit one.

Despite my ongoing best efforts, I have never seen any exception to this rule.

Even the fanciest pantsed distributed databases, with all the Rafts and Paxoses and red/greens and active/passives and Byzantine generals and dining philosophers and CAP theorems, are subject to this. You can do a bunch of math to *absolutely prove beyond a shadow of a doubt* that your database is completely distributed and has no single points of failure. There are papers that do this. You can do it too. Go ahead. I'll wait.

<several PhDs later>

Okay, great. Now skip paying your AWS bill for a few months.

Whoops, there's a hierarchy after all!

**You can stay in denial, or you can get serious.**

Western society, economics, capitalism, finance, government, the tech sector, the cloud. They are all distributed systems already. They are all in severe distress. Things are going very bad very quickly. It will get worse. Major rework is needed. We all feel it.

We are not doing the rework.

We are chasing rainbows.

We don't need deregulation. We need better designed regulation.

The major rework we need isn't some math theory, some kind of Paxos for Capitalism, or Paxos for Government. The sad, boring fact is that no fundamental advances in math or computer science are needed to solve these problems.

All we need is to build distributed systems *that work*. That means decentralized bulk activity, hierarchical regulation.

As a society, we are so much richer, so much luckier, than we have ever been.

It's all so much easier, and harder, than they've been telling you.

Let's build what we already know is right.

**, where AI runs on us, not the other way around.**

[Tailscale](https://tailscale.com/)

**You can find me on Bluesky.
Or subscribe with RSS.**
