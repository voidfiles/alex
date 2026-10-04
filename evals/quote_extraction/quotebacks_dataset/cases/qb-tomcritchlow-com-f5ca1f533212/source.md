# A Text Renaissance

There is a renaissance underway in online text as a medium. The Four Horsemen of this emerging Textopia are:

- [Roam](https://roamresearch.com/), a hypertext publishing platform best understood as a medium for composing conspiracy theories and extended universes.
- [Substack](https://substack.com/), a careful and thorough ground-up neoclassical reconstruction of the age-old email newsletter.
- Static websites, built out of frameworks like [Jekyll](https://jekyllrb.com/)or[Gatsby](http://gatsbyjs.org)(full disclosure: a consulting client).
- And finally, [Threaded Twitter](https://twitter.com/vgr/status/1205983999274840064), a user-pioneered hack-turned-supported feature that has wonderfully revitalized the platform.

I want to take a stab at lightly theorizing this renaissance. And also speculating, in light of this renaissance, about what might be the eighth and penultimate death of blogging. And the future of books. So it's going to be a sprawling, messy hot take on the State of Textual Media. Or at least a simmering take, since I've been thinking about this stuff for a year on the backburner.

The text renaissance is an actual *renaissance.* It's a story of history-inspired renewal in a very fundamental way: exciting recent developments are due in part to a new generation of young product visionaries circling back to the early history of digital text, rediscovering old, abandoned ideas, and reimagining the bleeding edge in terms of the unexplored adjacent possible of the 80s and 90s.

I imagine, to traditionalists already bemoaning the slow decline of print-based media like books, newspapers, and magazines, these technologies I want to talk about might seem like the four horsemen of the apocalypse. But whether they strike you as renaissance or apocalyptic technologies, they're here, so let's meet them.

### Roam

Roam attempts to implement a near-full conception of hypertext as originally conceived by visionaries like Vannevar Bush and Ted Nelson. I've been using it for a couple of months now. It's a revelation what a thoughtfully implemented version of a powerful vision can do to unexpectedly transform something you think you understand deeply at a  *Fingerspitzengefühl* (finger-tips feeling) level, like I think I do writing.

On the surface, Roam looks like a cross between a slightly weird wiki and a note-taking tool like Evernote. It's not. It implements a few key features of 1980s vintage hypertext visions -- block-level addressability, transclusion (changes in referenced blocks being "transfer-included" wherever they are cited), and bidirectional linking -- that utterly transform the writing experience at the finger-tips level. You end up organizing high-level structure as you work at fleshing out low-level chunks of information, because the UX collapses high and low-level thinking into a single behavior.

So you can write, structure, organize, refactor, bundle/unbundle, all in a single subconsciously learnable flow. You don't have to think consciously about this: it gets compiled down to finger-tip skill as you use it. This is the sort of product I was dimly groping around for, and trying to build at Xerox 10 years ago. I wasn't smart enough to pull it off, and back then, the technology wasn't there either anyway. Now the tech is there, and there's someone on the scene smart enough to pull it off.

I met up with Roam founder Conor White-Sullivan last week in San Francisco and had a nice long walk-and-talk chat around the Mission with him. People who pull off impressive feats of visionary product engineering often don't quite recognize what they've done, but that's not the case with with Conor. He knows what he's doing, he knows the history (aka [idea maze](https://cdixon.org/2013/08/04/the-idea-maze)) of the product he's built, and he's got the opinionated approach I look for when adopting a commercial product. He's also nailed the essential message-of-the-medium use case of Roam: conspiracy theories. Or alternately, extended-universe building. We're in a fake-news world and we might as well get good at it. *Good* in both senses of the term.

It can also do note-taking, workflows (like kinda-sorta competitor Notion), and wiki-like knowledge management, but those use cases are not as interesting to me. Conspiracy theories and extended universes, in the best senses of those terms -- escaped reality construction might be the general category -- is what Roam *wants* to be about.

The name, incidentally, is a play-on-words joke apparently. As in Rome wasn't built in a day.

### Substack

RSS had its rise and fall, going from seemingly promising consumer technology to limited-use backend plumbing. Email has now decisively reclaimed its dominant role as the last mile of push communications.

Email newsletters are as old as the internet, and as far as dinosaur technologies go, email appears to be unkillable. For a while it looked like Slack would do it, but sadly, Slack went too corporate to realize that possibility.

Email today is now less a communications medium than a communications compile target. It's a clearinghouse technology. It's where conversations-of-record go, where identity verification happens, where service alerts accumulate, and perhaps most importantly for publishers, where push-delivered longform content goes by default. It is distributed and federated, near universal, and is not monopolized by a single provider. Now that a constellation of other product categories have hived off around it in the last two decades, it's finally finding its own true nature.

The publishing side though, has always been rather janky. In the 90s people ran their own list-servs. In the aughts, as permission marketing took off and the spam wars started, traditional list-servs couldn't really keep up and email newsletters became contested territory in the arms race between marketing-communications platforms like Mailchimp and spam-filter algorithms on email clients like Gmail.

In the early tens, while blogging reigned and RSS was not dead yet as a consumer distribution mode, and twitter hadn't become dominant in the link economy, email newsletters for *writing*, as opposed to marketing, languished. They became associated with desperation: spammy-hacky popups on sites trying to get your email by any means necessary. Permission marketing evolved from Seth Godin's original noble conception to "Permission" marketing in scare quotes.

The reversal began with [TinyLetter](https://tinyletter.com/), but that got bought out by Mailchimp (and began to be viewed, correctly, as business-model compromised).

Enter Substack. Substack, by eschewing the marketing communications (MarCom) market entirely, and focusing on writers people actually wanted to read, reversed the perceptions of the technology. Instead of trying to scam people into giving you "permission" to send them emails, Substack said, why not charge them to subscribe. I've moved 1 of my 2 active newsletters (Breaking Smart, with about 7300 subscribers) from Mailchimp to Substack, and started a new one there (Art of Gig, currently at 1756). I'll probably move my auto-generated-from-RSS ribbonfarm newsletter there too. I've left it on MailChimp for the moment, because moving it would mean de-automating it.

By offering a seamlessly integrated email, payment integration (Stripe is a big part of all these revolutions), and no-design-needed opinionated web presentation, Substack managed to basically resurrect a zombie category of text media that hadn't really existed in this kind of pure form since the 90s.

You could kinda hack it together, but it was hardly easy. The case of OG pioneer of the sector, Ben Thompson, is the exception that proves the rule. His popular [Stratechery](https://stratechery.com/) newsletter has great content, but is a technical Frankenstein composed of WordPress, Mailchimp, Memberful, and Stripe. I tried briefly to set up that configuration myself a few years ago, but gave up on it as too high-maintenance.

Last week in San Francisco, I also dropped by the Substack offices to chat with founders Hamish McKenzie and Chris Best. As with Conor at Roam, I came away with the impression that they knew what they were doing, and had the right opinionated attitude towards it. They are also (wisely) hedged against email as the last mile, and are paying as much attention to the web experience as the email experience.

Substack is now a serious part of my own activities, including a serious part of my income. I'm currently making nearly $17,500/year off [Art of Gig](https://artofgig.substack.com/). I will definitely be doing more with the platform, the only question is how and when, not if.

### Static Websites

Static websites are of course, the original kind of website. The qualifier *static* wasn't even necessary in the first few years as that was the only kind of website you *could* build.

In the 90s, we had CGI (Common Gateway Interface) based dynamic websites. They were a horror to build and maintain (I worked for a major CGI-Perl era site briefly in 2000-01). CGI eventually evolved into the modern database driven website. Commonly using descendants of the LAMP stack (Linux, Apache, MySql, Perl/PHP). Today the webserver might be Nginx instead of Apache, and the scripting layer might be Ruby or Python, and you might be running in some sort of container in the cloud instead of a Linux server you administer.

But through nearly 25 years of evolution, the basic *idea* of a destination content website hasn't really changed from a publisher point of view.

Websites have just gotten a lot more reliable, stable, and high-performance. And for most purposes, you don't need to roll your own website. You can use something like WordPress that implements a content management solution using the LAMP stack.

And high-end technologies like CDNs (content delivery networks) are now a standard part of serious websites.

This website, for instance, runs on a hosted WordPress platform called WPEngine that costs an arm and a leg (more on that in a bit), but is high-performance, secure, includes a seamlessly integrated CDN, and doesn't crash under big traffic spikes like the one I just experienced with the Internet of Beefs article. In the early years, ribbonfarm would promptly crash under mildly viral conditions. Today I pay an order of magnitude more for hosting, but basically don't have to do any thinking or mucking about in the backend to keep things running. We've come a long way.

But there is a sense in which this is a bad, baroque, equilibrium. If you open up the code view of any modern webpage, it will be an unreadable mess of javascript, html, and weird shit loaded from all over the place.

The new static webpage model takes a fundamentally different approach. The name is deceptive. Though the page delivered is a clean, simple static page, the backend is, if anything, a hyper-dynamic stream.

Frameworks like Gatsby (founded by my longtime friends and new clients Kyle Matthews and Sam Bhagwat) essentially assemble pages together on the fly from all over the place, via a just-in-time compilation stream piping into React. The result is blazing-fast websites that can be changed easily, but *look* static. In particular, they can evolve too fast to run off a "backend database" as such. Instead they do something that looks more like using the entire cloudy internet as a backend. The "server" behind a Gatsby style page is more like a temporary cache and assembly/staging area than a traditional backend.

What all this technical magic means for content publishers is that finally, after 20 years, there is now a real, serious alternative to WordPress for building content websites. It is an alternative in a real sense: it is a new medium from the publisher point of view, and you have to learn how to create content for it. While you *can* bolt it onto something like WordPress (what's known as a headless-CMS strategy), that's not the main attraction.

I see several promising young writers already moving away from the blog as the main vehicle for online written expression, and building bespoke sites with weirder, more experimental structures, using Gatsby and its kin as the foundation.

There has of course, always been a small subculture of diehard bare-metal-ists who eschewed the blogging stack in favor of rolling their own sites, no matter how complex things got, but this goes beyond such geekery for the sake of geekery. Now it's geekery for the sake of creative optionality.

Unlike Roam or Substack, this is not yet an entirely consumer-friendly technology. So right now, though it is exploding in popularity, Gatsby is primarily being used by serious programmers, often in corporations or design shops. You have to get fairly hands-on, and the required skills are about 3x harder to learn than running your own blog was in 2007. I made a very simple Gatsby website on Github-->Netlify just to try it out, and it's certainly beyond both my interest level to properly learn, and aptitude level for web-tech to get good at.

But it's going to get easier. Much easier. And then Interesting Times will ensue. The WordPress monoculture will start to shift and many more weird structures will begin to flourish.

### Threaded Twitter

Threaded Twitter is perhaps the most interesting and weird of the Four Horsemen of Textopia.

While the unwashed masses flock to non-textual media like TikTok, we Very Online cognoscenti know that Twitter is where all the history-making, universe-denting social media action really is. It is as close to a pure ideas-commons/digital public as we'll ever get.

A big part of the reason Twitter has ascended to this position is threading. The idea (originally known as tweetstorming) was invented as a simple workaround hack by Marc Andreessen back in 2014, to get past the 140 character limit. But a bunch of young pioneers rapidly turned it into a creative medium in its own right. Visakan Veeraswamy is among the best known at this point (he's publishing [a whole book of his threads](https://gumroad.com/l/friendlynerdbook) which I suspect is a first for the medium), but there are several others. At some point Twitter grudgingly started supporting threading as a feature (and in the process took control of how threads were displayed, an annoying but reasonable move). Services like [Threadreaderapp](https://threadreaderapp.com/) emerged to turn threads into longform documents.

In December, I accidentally instigated what ended up becoming an entire festival of threading, which I retroactively dubbed Threadapalooza 2019. I basically challenged people to do 100-tweet threads (optionally, in the case of mutuals, based on prompts from me), using the popular *1 like = 1 tweet* protocol (which I didn't invent, though many people assume I did). Here's a [meta-thread of 100 threads](https://twitter.com/vgr/status/1205983999274840064) that I compiled. A lot of the content was genuinely spectacular. There were excellent threads on architecture, macroeconomics, Trump, trauma and healing, and all sorts of other topics. Go browse the meta thread and read a few. If you've been thinking Twitter is a cesspool of civilizational decay, prepare to change your mind. It's pretty much the center of the renaissance.

My prompt went sort of viral, and several hundred more threads were created by people I don't know. All in all, it was a wonderful outpouring of deep reserves of creativity and knowledge, the likes of which I haven't seen online in a long time. Several participants turned their threads into blog posts, and in one case, [an actual newsletter](https://innovationatscale.substack.com/) (on Substack!), so I'm kinda proud of what I managed to provoke.

It's hard to convey what the hell happened during the two weeks the event was live, if you weren't on twitter. But with a spot of Tom-Sawyerish whitewash-the-fence flattery, bullying and cajoling, I got a bunch of people to join me in adding some meta-structure to the event, so on top of the threading frenzy, a sort of meta-event emerged.

It began with Dorian Taylor [writing a script to scrape the threads](https://gist.github.com/doriantaylor/f89caee7badb1581fd8b9799477fdcae) into a data hairball, which many others used to create visualizations.

Then Our Man in Russia, [Artem Litvinovich](http://orbides.org/), got in on the act and made a video showing how the action unfolded.

Then Ian Johnson, d3 maven, created this [really nice navigable dashboard-like view](https://observablehq.com/@enjalot/threadapalooza-2019) of the event.

Andrew Benson created a pretty consolidated visualization of the race:

Lars E. Schonander [did some crunching](https://theaggregate.substack.com/p/the-aggregate-december-23rd-2019) to create a whole bunch of more wonky visualizations of what happened: rate of Likes, Likes to Tweets ratio, a moving leaderboard etc. Here's a sample:

My own contribution to the meta-event, besides being the whitewashing-the-fence instigator and compiler of threads, was to do ongoing cheerleading featuring the mascot of the event, Ascii Text Critter.

This is the current state of the art. Threading is clearly a very rich and complex medium, with a huge amount of potential.

We've barely scratched the surface of what's possible. If an almost-accidental event with some random volunteer hacking can lead to such a rich expression of creativity in both content and container, there's a lot more to explore and develop here. All the hacks people pulled together suggest that if the technology comes together in the right way, Threadapalooza could become the template of a whole new kind of virtual conference. If I were 20 years younger, I'd be trying to create a startup to build such a product.

Given Twitter's track record though, I'd bet that the threading revolution will not actually unfold on Twitter itself. There's a 50-50 chance they will do something boneheaded to mess up the potential, and starve out any products that attempt to build anything good on the quicksand of insecure attachment that's the Twitter API.

So other products will actually take this energy places. But one way or another, the future is going to be threaded.

My own personal attitude towards Twitter is one of continued bewilderment, though I've been on it since 2007 and have 4 accounts on it (the largest, @vgr, with >30k followers at this point). I think I'm fairly good at twitter, but I still don't quite know what I'm doing there or why. Perhaps that's for the best.

## The Enablers

One reason all this is happening now is that a set of interesting enablers are emerging simultaneously, on technological, economic, and cultural fronts.

### Technology

On the technological front, we have: React, Graph databases, next-generation languages like Clojure (the language Roam is written in), and a shifting perception of Javascript: instead of being viewed as a janky front-end language, it is now viewed as a mature "low-level" language, available on both frontend and backend (via Node) that's more a compile target than something you hand-code in. These technologies in turn rest on a new generation of hardware and cloud infrastructure.

There may be more interesting pieces of the puzzle coming down the pipeline. For example, my buddy Dorian Taylor (who wrote the Threadapalooza scraper linked earlier) has been quietly [building up a usable descendent of SemWeb technologies](https://doriantaylor.com/the-symbol-management-problem) for textual content management. There's a lot more like this going on quietly in the background I think.

Machine-learning driven technologies that can really soup up text are almost here. Two in particular are worth watching:

- **Automated transcription**: The podcast boom (and to a lesser extent, the video boom on YouTube) currently exists almost entirely as an artifact of two social phenomena: commuting and low-cognitive-demand chores, both of which call for a low-information-density ambient background information flow. It is the conversational equivalent of elevator music (convo-muzak? convozak?). When transcription gets good enough, it will create another feedstock for text, and the backward coupling will create a whole new subculture within audio/video, of creators who are solving for higher-information-density text distribution in addition to/instead of, ambient convozak.
- **Machine-generated text**: GPT-2 is a genuine breakthrough in text-generation. I've been trying, with the help of programmer collaborators, to turn myself into a bot for years now, and finally, with GPT-2, an algorithm can sort of[generate tweets that sound like me](https://twitter.com/hashtag/vgr_gpt2?src=hashtag_click)(ht Will Darwin,[here's how he did it](https://www.willdarwin.com/blog/machina-1/)). It's fascinating and surreal, and I can't wait to properly integrate that into my writing somehow.

### Economics

On the economic front, it is hard to overstate the profound effect Stripe has had on at least the English-language content ecosystem. Thanks to the availability of a solid, trustworthy, and well-designed payment processing solution, a great many ideas that used to be hard, annoying, or impossible can now be tried out.

Stripe is important because it allows content technologies and media to be built ground-up with monetization philosophy in place at the foundational level. It doesn't have to be a janky bolted-on piece of the puzzle.

Ten years ago, payment integration models were so bad \*cough Paypal cough\* that it created an adverse selection effect on textual content: you had to *really, really* care more about money than writing to deal with the jankiness of it all. This meant, of course, that only the most mercenary and shallow content creators pursued monetization seriously. The positive impact of PayPal (and the PayPal mafia) is widely recognized. I think we're only now beginning to recognize the negative externalities created by it being the main payment processor for 15 years. It took the rise of a better product to show us what good payment integration can do to media.

Now payments have basically been solved in a seamless enough way (modulo annoying EU GDPR crap) that it should lead to a different sort of flourishing. It won't be the open, free as in beer/free as in speech text internet with an open source ethos inherited from open source code. But it will likely be something much bigger and more interesting once money flows get built into the plumbing deeply.

There's also crypto over the horizon, but that's going to take another 5-6 years I think to truly affect the media landscape. I did some early experiments with ERC20 tokens and such, as did others, and it's in the wait-and-watch category for me.

### Culture

On the cultural front, thanks to the toxicity of the Internet of Beefs, and the rise of what I've called the Cozyweb, the zeitgeist is very friendly to content technologies that *don't* attempt to "democratize broadcast reach" as it were.

A common feature of all four horsemen of the textopia, from the publisher point of view, is that they trade quantity for quality. You want a more controlled, better gated, more intimate, and more financial relationship, with smaller audiences.

You want to get away from flash-flood virality and towards long-term relationships. I've written enough about this aspect elsewhere, so I won't dwell on ot.

## The Eighth Death of Blogging

On the destruction side of this cycle of creative destruction is blogging.

The death of blogging has been announced routinely every couple of years since 2000, and since I've been participating, starting in 2007, I've always concluded the death-sayers were mistaken. We're going through another such cycle now, but this time I think it really is different.

If blogging is a cat with nine lives, this is probably the eighth death.

The biggest reason is operating cost at larger scales. WordPress now serves something like a third of all websites, last I checked, and is a highly complex beast of a CMS that can serve up photo portfolios, ecommerce sites, business websites, etc. It has evolved far beyond basic reverse-chronological RSS-spitting blogging. A vast universe of themes and plugins exists, as does a sophisticated managed hosting industry with staging, fault-tolerance, automated upgrades, solid security, integrated CDNs, etc.

That's part of the problem. I use one such service, the Cadillac of such services in fact, WPEngine. Unfortunately, in the last 12 months, for the first time in over a decade (after my first couple of years), Ribbonfarm is going to post a small operating loss.

Here's a snapshot of the unit economics of running a site like this, which you should be able to parse if you're marginally financially literate:

The headline is that with traffic roughly steady, operating costs have gone up 45% (largely due to WPEngine doubling its overage charges from $1 to $2 for every 1000 visits above your plan base), while my Amazon Affiliate income (my main offsetting revenue stream) has dropped by about 26% for unclear reasons. There's a lot of band-aid fixes and optimizations possible (moving to a cheaper host, doing more with affiliate programs or advertising) but the writing on the wall is clear. This is no longer a cheap, indie-scale technology past a fairly modest success bar. One way or another, you'll pay for the privilege of being a blogger.

Here's what traffic's been up to in the meantime. You'd think it's good news, but it's not really. The huge spike is the [Internet of Beefs](https://www.ribbonfarm.com/2020/01/16/the-internet-of-beefs/) article, my first hit of this magnitude in a few years (the last one was [The Premium Mediocre Life of Maya Millennial](https://www.ribbonfarm.com/2017/08/17/the-premium-mediocre-life-of-maya-millennial/) in 2017). Without it, I'd probably not have gone into the red. A decade ago, I'd have been over the moon about it. Now I'm like, dammit, this screws up my operating cost structure and I don't give a shit about the exposure anymore. The spike cost me $324 in overages last month alone. And so far, there's been nothing in the profit column attributable to it.

One element of my broader response to the declining marginal value of virality (both financial and psychological) has been [my experimentation with blogchains](https://www.ribbonfarm.com/blogchains/), a format that a handful of other bloggers have also adopted. I came up with it partly as an anti-viral strategy to actively curtail and reverse traffic growth. I didn't want to unintentionally end up in a bleeding-red go-big-or-go-home regime, since I have no appetite to go big.

Another is my experimentation with getting rid of headlines (ie a human-centric discovery/addressing/packaging layer). You might have noticed that I'm doing a new blogchain with titles in the format MJD xxxx. It's the opposite of clickbait. It's active click-hostility. Things without evocative names have less of a chance of going viral and causing big spikes in hosting costs.

This might sound stupidly self-sabotaging and/or snowflakey and/or humblebraggy, but I really don't want the problem of managing a site where success in content terms might mean a choice between slow ruin and unsavory monetization models in financial terms.

The second/third order payoffs of exposure, consulting gigs etc. is not as worth it as you'd think. And it's really not as easy to scale this sort of operation as you might think. Between sites of ribbonfarm scale, and the lowest tier of "professional" media sites that are effectively magazines with a writing staff, there is a nightmare zone where monetization is janky and hard, business models are unstable and ugly, relationships with audiences are in a Patreon-ish badlands zone of crowd-sourced thought policing, and the technical administrative work involved in keeping the whole thing going is annoying and unrewarding.

I'm still thinking through what to do about this situation and where to go next personally, in a way that allows me to write what I want, without creating a financial discipline management job for me I don't want, or accidentally creating a media startup I don't want to run.

## Books, eBooks and Zines

I want to round out this whistelstop tour of the textual media landscape with a very brief note on books and ebooks. I have self-published one print book ( *Tempo*), and

[9 ebooks for the Kindle](https://amzn.to/2HOm4Ki). Together these net me a few hundred dollars a month in royalties. Decent pocket change, and far more than median traditionally published authors make, but it isn't going to earn me any mansions.

If I'm being honest, books have become an increasingly unattractive medium for writers like me who primarily developed a voice online. I do not write (or want to write) things with large-scale mainstream appeal. I do not crave the cachet or mainstream legibility that comes with big-publisher-backed books. I have no interest in riding a bestseller to TED or Davos.

More importantly, I don't quite enjoy the experience of retreating for long periods to write 35k-100k words in open loop mode. I think my limit for open-loop writing is about 14k words. For the book on temporality I'm working on now, I'll probably serialize it online in some form before trying to put it together as a book.

The whole point of that 35k-100k open loop mode is to target *print* books, which have unit economics that lend themselves to 35k+ word dead-tree containers. I'm ambivalent at best about having my stuff available in that form factor. It's not like I do richly illustrated or complex-layout types of writing. There's really no good reason for most people to prefer paper for *my* writing, and several reasons against (paper books having net higher carbon footprints being one of them)

But worst of all, books are an absolute bitch to produce (whether you self-publish or work with a publisher), with print books being an order of magnitude more work, and coming with the additional burden of distribution risks. For someone spoiled for a decade by the experience of hitting a button to publish, it seems like a Sisyphean task with dubious rewards.

I typeset *Tempo* myself in LaTeX and then paid a friend (thanks Adam) to design and add a cover, fine tune the PDF for PoD print-stability, and generate the ebook for the Kindle.

For the next two I hired a friend (thanks Jane) to go from database to html to LaTeX to ebook, eschewing the print option altogether.

The next 6, another friend (thanks Jordan) set up a sort of ebook editorial-to-production assembly line for me, without LaTeX or PDF as an intermediate.

On my to-do list is to make that assembly line even more efficient, including creating the option of going to print-on-demand easily where that's a good idea. It's a problem startups etc have been attacking for a decade, and it's still not close to good enough. Every year or two, some excited startup founder emails me promising to make me rich by book-izing my writing. They never have the solution and can rarely answer even my most basic questions.

The tech part is getting slowly easier. Adding solid design and editorial production values is the hard part, since that's not automatable yet, but it's within reach. This whole area is something of an expertise area for me, since I worked on aspects of it for years at Xerox and produced a print-on-demand book way back in 2000. It's a total grind of a problem. Eventually someone with a sufficiently big warchest will crack it properly. When that happens, I'll be in line waiting. Until then, it's a low-priority personal-hack problem.

Are books worth it?

Ebooks for sure. They allow for a kind of ludic reading experience that browsers and apps still don't deliver. I don't get much out of making them besides a small stream of money, but readers seem to appreciate them.

Print books? The jury is out I think. I think print is worth it for comic books, art, photography, and complex textbooks. For anything else, ebook-by-default, print-by-exception might be a good standard.

I honestly wouldn't care if I never appeared in print again, though my parents are hoping to see another print book out of me And many readers seem to have a kind of sentimentality about print that I don't really share, but am happy to feed. I wouldn't mind producing print books if it were technically trivial to do, financially lucrative compared to ebooks, and the carbon costs could be meaningfully mitigated. But it's honestly not a high priority.

I've personally been using libraries a lot more in the last few years, for both print and ebooks. But increasingly, I don't like either owning books, or getting print books from the library (who wants the flu germs). I think I've gone fundamentally digital-and-online at some deep amygdala level.

I want to throw in a mention of zines. That's one print format that *does* interest me. It seems like an intriguing new medium. Former ribbonfarm contributor Sonya is doing an experiment [producing a zine a month](https://www.sonyasupposedly.com/supposedly-zines/).

Zines are on my watchlist as an interesting medium. I have zero interest in the artisan production and fulfillment experience as a producer, but there's something very zeitgeisty going on there. The message of that medium is interesting.

## Text in a Hypermedia Context

Most attention in the consumer media technology world tends to focus on the latest, most sophisticated media that we can create with networked computing technologies. Right now, the mainstream technological frontier lies in encrypted p2p messaging (WhatsApp, Signal, Telegram) and short-form video (TikTok).

VR, AR, deepfakes (as a creative medium), and natural-language text-generation (in particular the deep learning algorithm known as GPT-2) are inching ever closer to the mainstream.

Podcasting is approaching a sort of maturation plateau with the rise of both sophisticated toolchains and maturing automated transcription technologies (such as [otter.ai](http://otter.ai)). It's where blogging was in 2012 or so.

All that is important, very important. I'm personally invested in all of it. I have an experimental monologue podcast going over at [Breaking Smart](https://breakingsmart.substack.com/), with another conversational one in the pipeline. I am working on [a VR game](https://simmer.io/@maze_project/~9fe36f74-a57d-133f-4d65-6765889892ed) with a couple of collaborators. And as I mentioned earlier, I have been trying to [turn myself into a GPT-2 bot](https://twitter.com/vgr/status/1224862448630370304?s=20) (with [help from Will Darwin](https://www.willdarwin.com/blog/machina-1/)). But in each case, those are evolving Version 0.1 stories. The focus is on the technology more than the content.

Text though, is definitely going through a renaissance, and as primarily a producer of text, that's what interests me the most. What comes out the other end may or may not look anything like blogging. It might be a case of a New Blogging as an Elder Medium in an explosion of new textual media. Or it might be a case of Blogging is Dead, Long Live Blogging. Or something else altogether.

Right now, I'm actively trying to reimagine my whole junkyard of a mini media empire from the ground up, thematically, structurally, and financially. We'll see what sort of new Cunning Plan™ I land on. The Four Horsemen of Textopia will certain play a growing part, as will some random mix of newer technologies.
