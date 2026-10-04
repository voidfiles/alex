I’m software bonkers: I can’t stop thinking about software. And I can’t stop building software.

I’ve always been opinionated about how software should work. Mainly, it should be [fast](/essays/fast_software/). The bounds of it should be “knowable.” The contract you have with it should be “sane” (i.e., you just own it). But I’m busy, and I’m an OK-but-not-great coder. So all of these software opinions largely stayed locked in my noggin. Then, a year ago, Claude Code appeared.

[My first Claude Code project](/roden/102/#the-good-place) was to rebuild Twitter as I always thought it should be:

- All posts disappear in 7 days
  - But you can keep a post ”alive” by replying to it
- You can only post 2 times a day
- You can reply 20 times a day (discussions are encouraged!)
- All images appear in 1-bit black and white until clicked on (at which point they transition to color or full-spectrum grayscale)
- The timeline is non-algorithmic, just simple reverse chronological ordering

Surprise! It’s really lovely. And members from my [membership program](/membership) have used it this past year to form a community the likes of Ye Internet of Yore. We share nice, inspiring things, and are nice and inspiring to one another.

My membership program is called [SPECIAL PROJECTS](/membership/). I don’t use Patreon or Substack, I built my own platform atop Memberful. Why pay a company a monthly fee to be hamstrung by how they think your program should look or be run? Each month, for the last few years, I’ve added new functions to the members’ site. Most recently, using Claude Code I built a tool to auto-generate granular chapters for my members-only livestream Q&As. And then I built a tool to index the forty hours or so of video I’ve amassed these last few years, allowing members to search the archive. When they click a question, the precise playback moment pops up in the video from which it’s pulled. It’s sort of amazing and is exactly the sort of thing I would have thought of a year ago, but never built.

With Claude, I’ve built a host of software like this. Mostly small tools for myself — programs that instantly append copy buffers to text files (I keep a running file of nice things people write to me called `notapieceofshit.txt`) or quickly perform live currency conversions. Small utilities that I use multiple times a day and hundreds of times a year.

**But it’s been this last week, in a heated tax season jag, that I’ve gone most bonkers: I’ve built the accounting software I’ve always craved.**

---

My situation is pretty unique. I’m dealing with multiple bank accounts in multiple countries. Constantly juggling currencies. Money moves between accounts locally and internationally. I freelance as a writer for clients around the world. I do media work — TV and radio. I make money from [book sales](/books/things_become_other_things/) paid by Random House via my New York agent, and I make money from book sales sold directly from [my Shopify store](https://shop.specialprojects.jp/). I run that membership program I mentioned, which generates a big chunk of my income. I have public and private investments. I have expenses that are paid by wires (everything is done by bank wire in Japan), and others paid by credit cards. I need to reconcile book sales by country for my Japanese accountant since I’m technically an exporter, making and shipping books from here.

Simply put: It’s a big mess, and no off-the-shelf accounting software does what I need. So after years of pain, I finally sat down last week and started to build my own. It took me about five days. I am now using the best piece of accounting software I’ve ever used. It’s blazing fast. Entirely local. Handles multiple currencies and pulls daily (historical) conversion rates. It’s able to ingest any CSV I throw at it and represent it in my dashboard as needed. It knows US and Japan tax requirements, and formats my expenses and medical bills appropriately for my accountants. I feed it past returns to learn from. I dump 1099s and K1s and PDFs from hospitals into it, and it categorizes and organizes and packages them all as needed. It reconciles international wire transfers, taking into account small variations in FX rates and time for the transfers to complete. It learns as I categorize expenses and categorizes automatically going forward. It’s easy to do spot checks on data. If I find an anomaly, I can talk directly to Claude and have us brainstorm a batched solution, often saving me from having to manually modify hundreds of entries. And often resulting in a new, small, feature tweak. The software feels organic and pliable in a form perfectly shaped to my hand, able to conform to any hunk of data I throw at it. It feels like bushwhacking with a lightsaber.

It’s built in Python with Flask and SQLite and is, fundamentally, quite simple in pieces, but supremely powerful as a whole. (The magic of software is often how simple things are pieced together, more than whole hog reinventions.) I own the thing — the data, the program. There is no subscription. If I turn off Claude Code, it will keep working just fine. (And if I need to fix something, I can spin up Claude for a few bucks.)

Most miraculously: For the first time in my life, I have a dashboard that gives me a true, holistic view, of everything financial happening in my life and business. I’ve named my glorious contraption `TaxBot2000`. It is astounding. Let me repeat: *I built this in five days*.

It’s not perfect, and it’s not done, but it is already better than what I had been using for the last decade. Until now, I’ve leaned heavily on Quicken — closed-source subscription software that often fails to connect to accounts with two-factor-authentication, silently losing chunks of financial data. Previously, I’ve mixed Quicken with Google Sheets, using a stack of Google Scripts to move information back and forth between currencies and formats and countries. I’ve used Japanese accounting software to export Japanese bank accounts and credit cards, and then reconfigure and import them into Quicken as converted accounts. Anyway, complicated and weird and a bit quirky: my situation. For TaxBot2000? No problem. I don’t think I’ll open Quicken again.

---

Yes: I’m certainly an anomaly. In that I’m a big ’ole dork with a strong, lifelong love of technology and a degree in computer science, who is compulsively opinionated about software. TaxBot2000 would be mostly useless to many of you. It’s all custom to my particular situation, which basically nobody else in the world shares. Software for N of 1. Damn useful to me. My mania to build comes from a place of money trauma. Growing up without a buffer, I’ve always operated from a mindset of extreme scarcity. So this software is that, too — a transmutation of scarcity pathology into a honkin’ dashboard of financial truths, at both the 30,000-foot and micron levels.

I feel a strange lightness. I keep thinking of features, views, other things I want to demystify. My finances were always somewhat opaque — until now.

---

What does this mean for the future of software? I don’t know. (Nobody does.) Maybe we really should be shorting a bunch of SaaS companies. (Don’t worry, a host of new ones will take their place.) I’m canceling my Quicken subscription. It’s only going to get easier to build things like TaxBot2000. We’re still in the dorks-only phase of model-assisted programming, but I can imagine soon-to-arrive interfaces where you just drag and drop components while narrating your desires with your voice, the models able to perform the “brainstorming,” “planning,” and “work” — operations that can take ten minutes or longer today — in mere seconds tomorrow. There will be a fluidity to software in the future. Version numbers will be pointless. We’ll all have our own versions. Claude Code be our partner in production. As you imagine new features, Claude produces them. Why would we lock ourselves into someone else’s proprietary binary? Control over our data, and control over how we view and engage with it, feels like it will be utterly non-negotiable going forward. We owe all of these capabilities to the generosity of the open source community.

It’s strange times. Anyway, I’m mad for software right now. Bonkers. I can’t stop thinking about things to make, things to make *better*. And then I go and make them. There’s an energy around all this that is — truly — epochal. If you’re not playing with models like Claude, you should probably take a peek. It’s the time of building.

This essay, published March 2026. Thoughts? Email [me@craigmod.com](mailto:me@craigmod.com).

[![Craig Mod, his head, floating at the bottom of the article](/images/about/craigmod-headshot-2025-small-01.jpg)](/about/)

[Craig Mod](/about/) is a writer and photographer based in Japan. He's the author of the books [*Things Become Other Things*](/books/things_become_other_things/) and [*Kissa by Kissa*](https://shop.specialprojects.jp/products/kissa-by-kissa-6th-ed) and is a MacDowell, Ragdale, and VCCA writing fellow. His essays and articles have appeared in *The New York Times*, *Eater*, *The Atlantic*, *California Sunday Magazine*, *Wired*, *Aeon*, *New Scientist*, *Virginia Quarterly Review*, *The New Yorker*, *The Morning News*, *Codex: Journal of Typography*, and elsewhere.

He writes newsletters, oh yes, [newsletters](/newsletters): [*Roden*](/explorers/) & [*Ridgeline*](/ridgeline/).

The work on this site is supported 100% by [paid memberships](/membership/) and [book & print sales](https://shop.specialprojects.jp/).

Whatever you do, don't follow @craigmod on [Bluesky](https://bsky.app/profile/craigmod.com) or [Instagram](http://instagram.com/craigmod).
