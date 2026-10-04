# James Shore: You Need AI That Reduces Maintenance Costs

## You Need AI That Reduces Maintenance Costs

### May 10, 2026

I’ll get straight to the point: your AI coding agent, the one you use to write code, needs to reduce your maintenance costs. Not by a little bit, either. You write code twice as quick now? Better hope you’ve halved your maintenance costs. Three times as productive? One third the maintenance costs. Otherwise, you’re screwed. You’re trading a temporary speed boost for permanent indenture.

Oh, you want to know *why?* Sure. Let’s go for a drive. On a dark desert highway...

### Productivity is Determined by Maintenance Costs

Every line of code you write has to be maintained: bug fixes, cleanup, dependency upgrades, and so forth. I’m not talking about new features or enhancements. Just maintenance. For every month you spend writing code, you’ll spend some amount of time in the following year maintaining that code, and some in each year after that, forever, as long as that code exists.

Let’s say you asked a crowd of, say, 50 developers what those maintenance costs were. Using a technique called [Wisdom of the Crowd](https://en.wikipedia.org/wiki/Wisdom_of_the_crowd), you could get a reasonably accurate response.1

1You’re welcome to conduct your own wisdom-of-the-crowd survey! But it turns out that the specific numbers don’t matter for the overall point I’m making here.

Your crowd might tell you that, for each month you spend writing code, you’ll spend...

- 10 days on maintenance in the first year;

  *and*
- 5 days on maintenance each year after that.

If you were a particularly obsessive individual, you could spend hours making a spreadsheet modeling how those estimates affect productivity over time. [A spreadsheet like this](https://docs.google.com/spreadsheets/d/109XUgvOMClSoknyGr9MtjWvNSfdf6XYiD5fnSvGYTTU/edit).

The first month of a new project is glorious. You spend all your time building fancy new features.

The next month is slightly less glorious. A fraction of your time—not much, but a smidge—goes to fixing bugs and cleaning up design mistakes from the first month. In the third month, a smidge more. And the fourth month, the fifth, the sixth...

Eventually, it’s not glorious *at all*. According to our crowd’s maintenance estimates, you’ll spend more than half your time on maintenance after 2½ years. After ten years, you can hardly do anything else.

Halving the crowd’s maintenance estimates gives you three more years before you hit the 50% mark. Doubling them sees you below 50% in less than a year.

The lesson is clear. If you want a productive team, you have to focus on their maintenance costs.

### All Models Are Wrong

Do these numbers ring true to you? They do to me. In my career as a consultant, I specialized in late-stage startups, and they all had the exact problem shown in the graph above. About 5-9 years in, they’d notice their teams were no longer getting shit done, and then they’d call me.

Their teams weren’t *quite* as bad as the graph shows. Maybe their maintenance costs were lower. Or maybe... and this feels more likely to me... their maintenance costs were *exactly* that bad, and they papered over the problem instead. Maybe they:

- Decided not to fix every bug, or upgrade every dependency
- Added people when the team got slow... and then kept adding more, because it was never enough
- Scrapped it all and started over with a rewrite

There’s room to debate the precise maintenance numbers, but overall, the model feels right. If you’ve been around the block, you *know* this graph is true. You’ve seen how productivity melts away over time. You have the scars.

### What Does This Have to Do With AI?

Only everything.

Let’s say your team just started using [Rock Lobster](https://www.youtube.com/watch?v=n4QSYx4wVQg), the latest and greatest agentic coding framework, and it Doubles!! your code output! Woohoo! The code’s a bit harder to understand, though, and your team is drowning in pull requests, and you maybe kinda sorta teensy weensy don’t actually read the code before smashing the approve button. Like, at all. I mean, you skimmed it, during boring meetings, sometimes, and that’s gotta be good enough, right? LGTM, let’s get this shit done!

So now you’re producing two months of work in a month, and let’s say you’ve doubled how much each “month” of output costs to maintain. Next month’s maintenance costs *quadruple*.

Oh.

About five months after you start using Rock Lobster, your productivity is back down to where you started, and a few months after that, it’s *worse* than it would have been had you never touched Rock Lobster in the first place.

I’m not saying your AI doubles maintenance costs. Or productivity. This is an extreme example. But even if your AI produces code that’s *just as easy to maintain* as your human-written code, the productivity gains don’t last.

### You Can Check Out Any Time You Like2

Agents are expensive, and they’re only getting more so. Once your agent’s juice is no longer worth the squeeze, you might decide to save your pennies and go back to coding the old way. Like a caveman. With your *fingers*.

Ha! Joke’s on you! When you stop using the agent, all the productivity benefit goes away... but the added maintenance costs don’t! As long as that code’s still around, you’re stuck with lower productivity than if you had never touched the agent at all.

### The Passage Back

The math only works if the LLM *decreases* your maintenance costs, and by exactly the inverse of the rate it adds code. If you double your output and your cost of maintaining that output, two times two means you’ve quadrupled your maintenance costs. If you double your output and hold your maintenance costs steady, two times one means you’ve *still* doubled your maintenance costs.

Instead, you have to invert your productivity. If you’re producing twice as much code, you need code that costs half as much to maintain. Three times as much code, one third the maintenance.

*This* is the secret to success. All the benefits, none of the lock-in.

### Can We Kill the Beast?

I dunno. All my reading of [the finest news sources](https://news.ycombinator.com/) says that coding agents *increase* maintenance costs. Some people do say they help them understand large systems better. But big decreases in costs, of the size we need to see? No. Just the opposite.

That’s a problem. The model isn’t a perfect representation of reality, but the overall message is right. You need AI that reduces your maintenance costs, and in proportion to the speed boost you get from new code. Without it, you’re screwed. You’re trading a temporary speed boost for permanent indenture.

So, yeah, go ahead, chase improvements to your coding speed. But spend just as much time chasing improvements to your maintenance costs. Or you, too, will be trapped in Hotel California.

Such a lovely place.

Such a lovely face.

**Continue reading:** [Are You Getting Your Money’s Worth from AI?](https://www.jamesshore.com/v2/blog/2026/are-you-getting-your-moneys-worth-from-ai?source=reduce-maintenance-costs)

PS: This isn’t an anti-AI rant. There’s other levers to pull, such as AI that makes maintenance itself more productive, even if it doesn’t make the *code* more maintainable. I encourage you to [copy the spreadsheet](https://docs.google.com/spreadsheets/d/109XUgvOMClSoknyGr9MtjWvNSfdf6XYiD5fnSvGYTTU/edit) and play with all the levers in the model. See what happens when you change the assumptions to match your real-world situation.
