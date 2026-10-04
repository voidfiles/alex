## An appreciation for (technical) architecture

##### 10.20, Saturday 28 Mar 2026 [Link to this post](https://interconnected.org/home/2026/03/28/architecture)

Once upon a time I kept on meeting architects who had ended up working with the web.

I asked why. Some good answers:

- Architects think about how people move between spaces (pages) and what that means for user experience - *this was at a time when web designers often came from graphic design and drew more on single page layout*
- Architects think about negative space, and how what you put in a space shapes social behaviour – *this was at a time when web before the social web*
- Architects have to work with a lot of different disciplines to make something, and all of those people believe they’re the most important person in the room, and that’s what product teams are like too - *lol*

I’m not an architect but some of my favourite books are about architecture.

Here are three:

- [How Buildings Learn: What Happens After They’re Built](https://en.wikipedia.org/wiki/How_Buildings_Learn)(1994) by Stewart Brand, which popularised that pace layers diagram
- [A Pattern Language: Towns, Buildings, Construction](https://en.wikipedia.org/wiki/A_Pattern_Language)(1977) by Christopher Alexander, which is infinitely applicable when[designing for multiplayer](https://interconnected.org/home/2022/01/21/social_gradient)
- [101 Things I Learned in Architecture School](https://www.amazon.co.uk/101-Things-Learned-Architecture-School-ebook/dp/B08S74443T)(2007) by Matthew Frederick, gifted to me by architect-turned-designer[Matt Jones](https://interconnected.org/[https:/petafloptimism.com](https:/petafloptimism.com/)), a distillation of perspectives and practices that nudges me in a new way every time I open it.

Two things that architecture does have been on my mind recently: how it shapes understanding and how it shapes its own evolution.

**Information architecture**

It’s a rare designer who operates at both the macro of strategy and culture and organisations, and the micro of craft and taste and interactions.

[Jeff Veen](https://jeffveen.me) is one. I remember him saying to me once:
> Design is about creating the right mental model for the user.

*(Now clearly design is not only about that, but for the particular problem I took to Veen, he said precisely what I needed to hear to get un-stuck.)*

So I love thinking about the [primitives](https://interconnected.org/home/2021/12/09/primitive_design) of functionality and content for the user and how they relate, such that the user can reason intuitively about what they can do with the system, and how.

And this is an interactive process: for a first time user, how do they first encounter a system and how do they way-find and learn over time?

And this is a cognitive process: mental models are abstract; what we perceive is real. So how does understanding happen?

*(AI agents are using my software. Prioritise clarity over feels.)*

Don Norman wrote [The Design of Everyday Things](https://en.wikipedia.org/wiki/The_Design_of_Everyday_Things) (1988), much loved by web designers, and popularised “user-centred design.”

Norman also brought into design the term *affordance* from cognitive psychology. As coined by J J Gibson:
> to perceive something is also to perceive how to approach it and what to do about it

([as previously discussed](https://interconnected.org/home/2022/05/03/landscape)).

The best way to notice affordances is to notice where they go wrong! [Norman doors](https://99percentinvisible.org/article/norman-doors-dont-know-whether-push-pull-blame-design/):

> Some doors require printed instructions to operate, while others are so poorly designed that they lead people to do the exact opposite of what they need to in order to open them. Their shapes or details may suggest that pushing should work, when in fact pulling is required (or the other way around).

Whenever you see a PUSH label stuck on as an extra, it’s papering over a Norman door.

[I was delighted to encounter a Norman door irl this week](https://www.instagram.com/p/DWV72vsjc6y/?igsh=eHF3cWZtcDRvbWow).

So I’m stretching the definition of architecture here, to include this, but roll with it pls. Architecture is how things are understood.

Architecture is how things evolve – how they’re *allowed* to evolve.

There’s a beautiful housing estate on the top of a hill in south London.

[Dawson’s Heights](https://hiddenarchitecture.net/dawsons-heights-state/) (1964) is shaped like an offset double wave, and looks different on the horizon from every angle and with every change of the light. Yet up-close it’s human-scale too, despite its 10 storeys.

Lead architect Kate Macintosh wanted residents to have balconies, but this was regarded as
> wasting public money on unnecessary luxuries

…

Knowing that they would be removed from her designs for cost-saving, [she made them essential](https://c20society.org.uk/casework/dawsons-heights-the-italian-hill-town-in-dulwich):

> *all the balconies on Dawson’s Heights are fire escape balconies*, but they are also private balconies because the escape door is a “break glass to enter” type lock so you can securely use your balcony for whatever you like.

**Technical architecture**

So software architecture is also team structure - who needs to talk to who - but also how to make sure that doing something the quick and dirty thing way is also doing it the right way.

> Half of software architecture is making sure that somebody can fix a bug in a hurry, add features without breaking it, and be lazy without doing the wrong thing.

I think this goes for internal software architecture and for libraries that you import.

The thing about agentic coding is that agents grind problems into dust. Give an agent a problem and a while loop and - long term - it’ll solve that problem even if it means burning a trillion tokens and re-writing down to the silicon.

Like, where’s the bottom? Why not take a plain English spec and grind in out in pure assembly every time? It would run quicker.

But we want AI agents to solve coding problems quickly and in a way that is maintainable and adaptive and composable (benefiting from improvements elsewhere), and where every addition makes the whole stack better.

So at the bottom is really great libraries that encapsulate hard problems, with great interfaces that make the “right” way the easy way for developers building apps with them. Architecture!

While I’m vibing (I call it vibing now, not coding and not vibe coding) while I’m vibing, I am looking at lines of code less than ever before, and thinking about architecture more than ever before.

I am sweating developer experience even though human developers are unlikely to ever be my audience.

How do we make libraries that agents love?
