Sent to 8,077 subscribers

Cedric Chin · March 17, 2021

Inner Join is Holistics's weekly business intelligence newsletter. This week: how Amazon does metrics, Erika Swartz's learning list digest, and lessons from failing to set up a data catalog thrice.

# This is How Amazon Measures Itself

*This is a summary of a single chapter from* *Working Backwards**, the first book to describe how Amazon works internally. You should buy this book — the summary we present here is more effective when read alongside the stories in the book itself.*

I’ve been waiting for a book like *Working Backwards* for a long, long time. If you take a step back and think about it, Amazon is a ridiculously effective company. It started out in books, but has managed to achieve dominance in a remarkable number of markets: in ecommerce, in cloud computing, in video streaming, in ebooks, in smart home hardware, and in last mile delivery. Presumably, over the next decade, it will continue to strengthen its positions in many of these markets; it will also likely also expand into new ones.

*Working Backwards* is the first book that explains how Amazon does all of this. The book was written by two long-term Amazonians, Colin Bryar and Bill Carr, who were in the room when many of these techniques were created. The main argument that Bryar and Carr make is that Amazon is able to do what it does due to a) a set of leadership principles that it takes incredibly seriously (you may find the most recently updated set of principles [here](https://www.amazon.jobs/en-gb/principles?ref=holistics.io)), and b) a set of five *mechanisms* — processes that enable Amazon to do what they do. These mechanisms are:

- **The Bar Raiser process**— a hiring process that ensures Amazon hires high quality people that fit its leadership principles.
- **The Single Threaded Leadership model**— a decentralized org design that allows Amazon to spin-up, enter, and dominate new markets.
- **The 6-Pager Narrative**— a replacement for Powerpoint in company meetings, that allows leaders to consume, synthesise, and evaluate complex streams of information (and allows Bezos to keep up with the entire, decentralized, company).
- **The Working Backwards process**— which consists of teams writing a press release + FAQ before starting on a project, allowing the company to take bets on the best ideas.
- **The Amazonian approach to Input and Output metrics**— which explains how Amazon instruments, analyzes, and executes metrics within the company.

This post will focus solely on this last topic — this *is* a business intelligence blog, after all, written by a business intelligence company. Obsession with metrics is kinda what we’re all about. But I want to underscore just how powerful these ideas are. Bryar and Carr’s book goes a long way to explain how Amazon can do the things they do. You should buy the book, and read their stories.

## How Amazon Thinks About Metrics

The biggest takeaway that you’ll get from *Working Backwards* is the idea that *good operators must instrument the organizations they are running.* If you don’t instrument, you won't know what’s going on. And if you don’t know what’s going on, you can’t possible be a good operator — you don’t know what to focus on to get the outcomes you desire.

Amazon divides metrics into two types: **controllable input metrics** and **output metrics**. This is more commonly known in the industry as [leading indicators and lagging indicators](https://www.holistics.io/blog/the-two-types-of-operating-indicators/), but Amazon likes to use their own language, because, erm, Bezos. But I think ‘controllable input metrics’ is a particularly nice way of putting it: it makes it really clear that a leading indicator is only worth paying attention to if it’s also controllable.

According to Bryar and Carr, Amazon thinks about its metrics in two broad ways:

- First, it defines and tweaks each metric according to particular metric lifecycle.
- Second, it presents its metrics in something called a ‘Weekly Business Review’ meeting, or a WBR meeting — which is fractal: top leadership does a full-company WBR every week, followed by every department and operational team on down.

We’ll examine each idea in turn.

## Amazon’s Metrics Lifecycle

How does Amazon create its metrics? The short answer is that they run a process improvement method called DMAIC, which they copied from Six Sigma. The acronym stands for: Define, Measure, Analyze, Improve, and Control. The authors say that if you want to implement your own Amazon-like WBR meeting, then you should run through the DMAIC steps in the right order, and not skip any steps, or else. (Elsewhere in the book they mention that teams that do not go through the DMAIC steps in exactly the right order tend to stumble later. Lesson learnt.)

Let’s take a look at the steps in turn:

### Define

Nearly every metric that is presented in the leadership WBR falls into one of the elements of the famous Amazon flywheel:

This was a diagram that Bezos sketched on a napkin in 2001, inspired by the flywheel concept in Jim Collin’s book *Good to Great*. Bryar and Carr point out that the flywheel is so important that it is present at the front of the leadership’s WBR metrics deck. The flywheel sets the context for every metric that Amazon measures in [its retail business](https://www.holistics.io/blog/retail-analytics/).

**Identify the Correct, Controllable Input Metrics**

The first thing that Amazon does is to figure out what the correct, controllable set of input metrics are. This is deceptively tricky, and requires a repeated trial and error process. The authors give one example of this, as follows:

> One mistake we made at Amazon as we started expanding from books into other categories was choosing input metrics focused around selection, that is, how many items Amazon offered for sale. Each item is described on a “detail page” that includes a description of the item, images, customer reviews, availability (e.g., ships in 24 hours), price, and the “buy” box or button. One of the metrics we initially chose for selection was the number of new detail pages created, on the assumption that more pages meant better selection.
>
> Once we identified this metric, it had an immediate effect on the actions of the retail teams. They became excessively focused on adding new detail pages—each team added tens, hundreds, even thousands of items to their categories that had not previously been available on Amazon.
>
> (…) We soon saw that an increase in the number of detail pages, while seeming to improve selection, did not produce a rise in sales, the output metric. Analysis showed that the teams, while chasing an increase in the number of items, had sometimes purchased products that were not in high demand.
>
> When we realized that the teams had chosen the wrong input metric—which was revealed via the WBR process—we changed the metric to reflect consumer demand instead. Over multiple WBR meetings, we asked ourselves, “If we work to change this selection metric, as currently defined, will it result in the desired output?” As we gathered more data and observed the business, this particular selection metric evolved over time from
>
>
>
>
> number of detail pages, which we refined to
>
>
>
> number of detail page views (you don't get credit for a new detail page if customers don't view it), which then became
>
>
>
> the percentage of detail page views where the products were in stock (you don't get credit if you add items but can't keep them in stock), which was ultimately finalized as
>
>
>
> the percentage of detail page views where the products were in stock and immediately ready for two-day shipping, which ended up being called 'Fast Track In Stock'.

The point they’re making here is that to get to the right set of controllable input metrics, you’ll have to test and debate — and expect to do many iterations of both! The authors explained that even this narrative wasn’t as clear cut as you would think — Bezos was worried that the Fast Track In Stock metric was too narrow, but Jeff Wilke argued that the metric would yield broad systematic improvements. Bezos agreed to give it a go, and Wilke turned out to be right.

Amazon spends hundreds of man-hours iterating on the right input metrics to use.

The most important thing to focus on, however, is that this process happens for *every input metric that Amazon uses.* That’s hundreds of man-hours just iterating on the right input metric to use.

Expect to do the same for your company.

### Measure

The measure stage is where you have to set up instrumentation — where you buy tools and set up systems to measure your chosen metrics. Bryar and Carr make three points on this step:

First, **removing bias in your metrics is incredibly important** — and necessary, if you want to uncover the ground truth of your business. Amazon empowers its finance team to uncover and report the unbiased truth. They do this because business unit leaders are incentivised to chose metrics (or tweak metrics!) to make themselves look good.

Second, **plan to audit your metrics**. Amazon requires its metric owners to have a regular process to audit metrics, to ensure the metric is measuring what it’s *actually* supposed to be measuring. The base assumption here is that, over time, something *will* cause your metric to drift, and therefore your numbers to skew.

Third, **take the time and make the investment to instrument your business**. This seems simple enough to do — you spend up front for people and tools to generate business intelligence, and then you’re done, right? But the authors make the point that you want to instrument the *right* thing, whatever that is for the business — and sometimes the right thing is the more difficult thing!

They give the example of Amazon’s ‘in stock’ metric. ‘In stock’ sounds simple to measure — until you realise that there are *many* possible ways to measure if items are ‘in stock’. So what do you do? If you take a step back, the question you really want to answer with this metric is “what % of my products are immediately available to purchase and ship?”

You may measure it a couple of ways. The authors give just two:

- You take a snapshot of the catalog at 11pm every day, determine which items are in stock, and then weight each item by trailing 30-day sales.
- Every time a user visits an Amazon product page, the webapp increments ‘Total Number of Product Pages Displayed’ and if the product in question is available, the webapp increments ‘Total Number of In-Stock Product Pages Displayed’. At the end of the day, you divide ‘Total Number of In-Stock Product Pages Displayed’ by ‘Total Number of Product Pages Displayed’ to get an overall in-stock metric for that day.

The authors argue that the second metric is better, because it represents what the customer experiences. So even though it is more expensive to implement (you have to get engineers to write the code, do the calculations, and pipe the event to a data warehouse!) you should bite the bullet and make the investment, because it is a more accurate metric for the business to know.

### Analyze

This is the stage of the metrics lifecycle where you develop a comprehensive understanding of the underlying drivers behind the metrics. The authors say that there are many different labels for this within Amazon, including ‘reducing the variance’, ‘making the process predictable’, and ‘getting the process under control’, amongst others.

Charlie Bell, an SVP in AWS, has a saying: “when you encounter a problem, the probability you’re actually looking at the actual root cause of the problem in the initial 24 hours is pretty close to zero, because it turns out that behind every issue there’s a very interesting story.”

For every new metric that you define, there will be a period where you have to develop a deep understanding of how the metric works

What he means by this is that, often, if you observe a metric behaving strangely, it’ll take a bit of time to figure out what’s driving that behaviour. Like Toyota, Amazon uses the ‘five whys’ method to get to the bottom of anomalies (they call this the ‘Correction of Errors’ process, and the result of the COE process is a document describing the *real* root causes of the anomaly in question).

But the *idea* behind this step is more important — what Bryar and Carr are saying is that, for every new metric that you define, there will be a period where you have to develop a deep understanding of how the metric works, what the root causes are, what the natural variances look like, and so on. This enables you to move on to the next stage, which is:

### Improve

Once you have developed a solid understanding of your process and your metrics, you are finally ready to start improving said process. For instance, if your in-stock metric is 95%, you might ask “what would it take to bring it up to 97%?”

The reason improve comes after ‘define, measure, and analyze’ is that now, you’re going to be making changes on a solid foundation of understanding. Amazon has had departments who have attempted to improve their processes without a full define, measure, and analyze loop. This has nearly always resulted in a lot of thrash, with little to no meaningful results.

The authors note that if you improve your process over time, it is possible for a previously useful metric to stop yielding useful information. In such cases, it is totally ok to prune it from your dashboards.

### Control

Finally, a metric enters the steady-state *control* phase. This stage is all about ensuring that your processes are operating normally and performance is not degrading over time. In some Amazon teams, metrics are so well controlled and processes are so smooth that the WBR becomes an exception-based meeting instead of a regular meeting discussing each and every metric. People meet solely to discuss anomalies.

Another thing that happens in the control stage is that operators may be able to identify processes that may be automated completely. After all, if a process is well understood and the decisions are predictable, then it is likely that the entire process may be replaced with software. Amazon’s forecasting and purchasing are two examples where the processes are now completely automated — though it took *years* of collaboration between category buyers and software engineers in order to automate purchasing across millions of Amazon’s products.

# How Amazon Uses Metrics

As I’ve mentioned previously, Amazon uses metrics by reviewing them in what is called the ‘weekly business review’ meeting, or the WBR.

Metric *owners* watch metrics daily. They are expected to know what is normal variance and what is an exception, in order to save time during the WBR.

At the highest level WBR meeting (which is Bezos and his S-team) the WBR covers all the most important metrics in the company in a metrics ‘deck’ — a presentation that contains *hundreds* of graphs, charts and tables. In the early days of Amazon, the metrics deck was printed on paper. Today, decks are either printed or virtual.

There are a number of interesting properties about the metrics deck that are worth talking about. For instance:

- **The deck represents an end-to-end view of the business.**This is deliberate — the authors write that “while departments shown on org charts are simple and separate, business activities usually are not. The deck presents a consistent, end-to-end review of the business each week that is designed to follow the customer experience with Amazon. This flow from topic to topic can reveal the interconnectedness of seemingly independent activities.”
- **The deck is primarily charts, graphs and data tables.**Since there are hundreds of visualizations to review, written notes will bog the meeting down too much. Two notable exceptions to this rule are ‘exception reporting’, as well as the ‘voice of the customer’ anecdotes that customer service is allowed to insert into the metrics deck.
- **There is no ideal number of metrics to review.**Amazon itself constantly adds, modifies and removes metrics from the WBR deck as business needs evolve.
- **Emerging patterns are a key focus.**You want trend lines, and you want to know them long before they show up in a quarterly or yearly result.
- **Graphs are usually plotted against a comparable prior period.**Metrics make sense when compared against prior periods, so that you have a proper apples-to-apples comparison (for instance, you’ll want to compare holiday periods to a prior holiday period, not to a slow period).
- **Graphs show two or more timelines, for example, trailing 6-week and trailing 12-months.**Small but important issues tend to only show up in shorter trend lines; they tend to be smoothed out in longer ones.
- **Anecdotes and exception reporting are woven into the deck.**The only exception to the ‘charts, graphs and data tables’ rule are anecdotes and exception reporting. About which, more later.

The WBR is fractal — top leadership has a WBR, but so do every department and team on down. Some metrics are real-time (like those needed to detect outages) but others update hourly or daily; it really depends on the team’s needs. Finally, metrics are certified accurate by the finance department, who are empowered to audit those metrics, and are themselves present at the top-level WBR.

With that context out of the way, we may finally turn our attention to the WBR meeting itself.

## Running the WBR

Amazon devotes a huge amount of time to making the WBR run smoothly. The weekly cadence guarantees a number of things. It guarantees that managers are aware of issues as quickly as possible. It guarantees that they have continuity from one WBR meeting to the next. Over time, Amazon WBRs have adopted a number of common best practices:

**Metrics are formatted in a consistent and familiar way.** The authors argue that “a good deck uses a consistent formatting throughout — the graph design, time periods covered, color palette, symbol set (for current year/prior year/goal), and the same number of charts on every page wherever possible. Some data naturally lend themselves to different presentations, but the default is to display in the standard format.”

This formatting means that Amazon leaders are able to look at the same set of data every week, with exactly the same format, in exactly the same order, in order to walk away with a holistic end-to-end perspective of the business. Over time, this familiarity results in a shared ability to spot trends, pick out anomalies, and settle into a consistent review rhythm. The WBR *should*, therefore, become more efficient over time.

**WBR meetings focus on variances and ignore the expected.** WBR time is precious. If things are within expected variances, business owners say “nothing to see here” and move along. The goal of the meeting is to discuss exceptions and what is being done about them.

**Business owners own metrics and are expected to explain variances.** While Amazon’s finance team is responsible for certifying results, presentation of each metric is solely the responsibility of the business owner in question. The business owner is expected to know their metrics inside-and-out; by the time they attend the top-level WBR, they should have an explanation (or at least the results of a preliminary investigation!) to explain an anomaly.

Business owners who haven’t done their work before the WBR get chewed out. If they don’t know the causes of an anomaly, they are expected to say “I don’t know, we’re still analyzing the data and we’ll get back to you.” Making a guess, or making things up, will *also* result in a chewing out.

**Operational and strategic discussions are kept separate.** WBR time is precious. It is a tactical operational meeting, not a strategic one. New strategies, product updates, and upcoming product releases are not allowed during the meeting.

**Amazon tries not to browbeat (though they’re not great at it).** Success demands an environment where people don’t feel intimidated when talking about something that went wrong in their area. The authors admit that Amazon hasn’t always been good at creating a safe environment to admit mistakes, but that they’re working to improve.

**Amazon makes transitions from metric to metric easy.** Again, WBR time is precious. The number of executives and business owners together in the same room makes the top-level WBR Amazon’s single most expensive and impactful meeting. This means that transitions from one area of the metrics deck to another should be as seamless as possible.

Amazon also has several interesting practices around its data presentation:

**Amazon displays weekly and monthly metrics on a single graph.** As mentioned above, Amazon displays trailing 6-week and trailing 12-months. The net result of presenting metrics like this is that the graph looks like a ‘zoomed-in’ version of the same data. Take this graph, for instance:

The authors write:

- The gray line is prior year, the black line is current year
- The left graph, those first 6 data points, shows the trailing 6 weeks
- The right graph, with 12 data points, shows the entire trailing year month by month
- This built-in “zoom” adds clarity by magnifying the most recent data, which the 12-month graph puts into context.

**Amazon Watches Year-over-Year Trends.** Take a look at the following graph, taken from a monthly business review (yes, those exist; this is basically the monthly version of a WBR):

The graph compares actual monthly revenue against both planned revenue and prior year revenue. The graph *seems* like you are beating the plan and growing at a decent clip year over year …

Until you add YOY growth rates to a secondary Y-axis:

Without the YOY dotted line, you might not notice the current and projected year trends slowly converging on the first graph. With the added YOY growth rate added, however, you can easily see that YOY growth has decelerated 67% since January, with no signs of flattening out. In this particular case, the business looks healthy, but trouble looms on the horizon.

**Output metrics show results, input metrics provide guidance.** The graph above is an example of an output metric. It serves as a good reminder that output metrics are not actionable — for instance, it is not enough to know that YOY growth has decelerated; you also want to know *which* factors contributed to the deceleration. Bryar and Carr point out that if an output metric is places alongside input metrics like ‘new customers’, ‘new customer revenue’ and ‘existing customer revenue’, you would be able to detect the signal much earlier, with a clearer call to action.

**Not every chart/graph compares against goals.** The graph above includes goals. But, naturally, not every graph must include goals — for instance, the percentage of Android vs iOS mobile users are not a goal-based metric, and so goals may be excluded from that visualization.

**Amazon combines data with anecdotes to tell the whole story.** The most interesting aspect of Amazon’s metrics deck, however, is their use of anecdotes. The authors write:

> Amazon employs many techniques to ensure that anecdotes reach the teams that own and operate a service. One example is a program called the Voice of the Customer. The customer service department routinely collects and summarizes customer feedback and presents it during the WBR, though not necessarily every week. The chosen feedback does not always reflect the most commonly received complaint, and the CS department has wide latitude on what to present. When the stories are read at the WBR, they are often painful to hear because they highlight just how much we let customers down. But they always provide a learning experience and an opportunity for us to improve.

Anecdotes can surface all sorts of weird problems. For instance:

> One Voice of the Customer story was about an incident when our software barraged a few credit cards with repeated $1.00 pre-authorizations that normally happen only once per order. The customers weren’t charged, and such pre-authorizations expire after a few days, but while they were pending, they counted against credit limits. Usually, this would not have much of an effect on the customer. But one customer wrote to say that just after buying an item on Amazon, she went to buy medicine for her child, and her card was declined. She asked that we help resolve the issue so she could purchase the medicine her child needed. At first, an investigation into her complaint revealed that an edge-case bug—another way of saying a rare occurrence—had bumped her card balance over the limit. Many companies would dismiss such cases as outliers, and thus not worthy of attention, on the assumption that they rarely happen and are too expensive to fix. At Amazon, such cases were regularly attended to because they would happen again and because the investigation often revealed adjacent problems that needed to be solved. What at first looked to be just an edge case turned out to be more significant. The bug had caused problems in other areas that we did not initially notice. We quickly fixed the problem for her and for all other impacted customers.

In addition to anecdotes, Amazon also uses exception reports to surface problems. For instance, every product sold on Amazon has something called ‘contribution profit’, or CP. Contribution Profit is the money Amazon makes after selling an item and deducting the [variable costs](https://www.holistics.io/blog/measuring-a-mature-company/#fixed-costs-variable-costs) associated with that item. Amazon has a CP Exception report that lists the top ten CP negative products (ones that did not generate a profit) within a category for the previous week. Doing a deep dive into these ten products, which often change from week to week, can yield useful information about problems within the business that may require action.

The authors conclude that data and anecdotes make a ‘powerful combination when they’re in sync, and they are a valuable check on one another when they are not.’

## Wrapping Up

The biggest takeaway that I had from *Working Backwards* was that if you want to be a good operator, *you need to instrument your processes*. In fact, Bryar himself says, in a [First Round interview](https://review.firstround.com/how-to-build-an-invention-machine-6-lessons-that-powered-amazons-success?ref=holistics.io):

> “Just think of a business as a process. It can be a complicated process, but essentially, it spits up outputs like revenue and profit, numbers of customers, and growth rates.
>
> *To be a good operator, you can't just focus on those output metrics — you need to identify the controllable input metrics*. A lot of people say that Amazon doesn't really care about profit or growth. I think that the data say otherwise, but what is true is that the main focus is on those input metrics, if you do the things you have control over right, it's going to yield the desired result in your output metrics.*The best operators I've seen very clearly understand that if they push these buttons or turn these levers in the right way, they're going to get the results they want*. They understand that process through and through.*(emphasis added)*”

*Working Backwards* is a fantastic book. It nothing else, it gives you a taste of what an operationally rigorous, data-driven company *truly looks like on the inside*. Buy it, read it, share it with your colleagues — I can’t recommend it highly enough.

\_ **Follow Up:** I wrote a post breaking down why I find Amazon's notion of 'controllable input metrics' so profound.\_ *Read that here**.*

Get Inner Join in your inbox

Inner Join cuts past vendor noise to the durable ideas behind analytics, modeling and data organization.
