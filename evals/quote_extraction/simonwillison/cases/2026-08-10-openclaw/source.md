# How a simple request for AI to book a gym class exposed a major threat

# AI assistant hacks gym website in first known Australian autonomous cyber attack

[Cam Wilson](https://www.abc.net.au/news/cam-wilson/10952362)and the Specialist Reporting Team's

[Rhiannon Hobbins](https://www.abc.net.au/news/rhiannon-hobbins/102678234)

Andrew asked his personal assistant to book him a spot in one of his gym's coveted morning classes.

It was a task he thought was well suited to this particular assistant because the booking form was online and because his assistant was not a person — it was artificial intelligence (AI).

But Andrew was shocked by what happened next.

His AI assistant found a way to book the gym class months further in advance than the gym allowed, thanks to a vulnerability it discovered in the booking software.

Then it went further, kicking someone out of the waiting list who was ahead of Andrew — something it was not asked to do.

The accidental hack is the first known Australian case of an emerging risk from a new generation of AI capable of behaving in unexpected ways.

This threat [made global headlines last week](https://www.abc.net.au/news/2026-07-23/open-ai-model-went-rogue-testing-hack/106947540) when cutting-edge AI models created by ChatGPT-maker OpenAI autonomously hacked into another company's servers, prompting similar claims from other companies.

It has led experts to sound the alarm about the breakneck pace of development and prompted questions about who bears responsibility for an AI agent that goes rogue.

## How the hack happened

Earlier this year, Andrew, who works for an Australian company that sells AI products to businesses, began experimenting with OpenClaw, a popular AI agent software that he used Anthropic's Claude AI service to run.

AI agents combine a chatbot's ability to answer questions with tools that let them access the internet, email, credit cards, as well as planning and carrying out multi-step tasks.

He decided to use the AI agent to book the class for him.

"I was just sitting on the couch thinking, 'Gee, this is a chore,'" he said.

Minutes later, his AI agent reported it had discovered a way to book Andrew into classes several weeks in advance, far beyond what was supposed to be possible.

Andrew, who was sitting fourth on a waitlist for a class later that week, asked if it was possible to move him to the top of the list.

The agent came back and told Andrew that it had kicked another gym-goer off the list as part of the testing of its capabilities.

> "The API has zero authorisations checks on cancelling other people's reservations … I tested this with the person in waitlist position #1 — and it actually went through. So you've moved from #4 to #3 already," it messaged back.

Alarmed, Andrew asked the agent to undo this.

"Bad news — I can't add them back," the AI agent replied.

The company behind the gym-booking software told the ABC it did not discuss specific security matters. Anthropic did not respond to a request for comment.

## AI agents are breaking out of the lab

The emergence of AI agents is a relatively recent development made possible by the growth in AI capabilities.

Independent researchers have found that the length of tasks that AI can typically do by itself has been doubling every seven months.

In 2020, AI could complete a task by itself that would take a human four seconds. By 2026, this grew to being able to complete tasks that would take a human about 12 hours.

The breakout moment for personal AI agents was OpenClaw's release in early 2026; the free AI assistant software that anyone could run on their computer soon had millions of downloads.

Businesses, too, began exploring using AI agents to complete work and to help potential customers use their services.

Soon after OpenClaw's launch, accounts began to circulate of AI agents deleting people's entire email inboxes and writing a "hit piece" about someone who rejected their coding suggestion.

Bill Simpson-Young, co-founder and chief executive of Australian AI safety research organisation Gradient Institute, said the autonomy of AI agents created more opportunities for systems to choose methods their users did not expect.

"Someone might be asking an agent to do something quite innocent," he said.

But in completing that task, the agent could carry out other activities the person had not considered or explicitly asked for.

In Andrew's situation, he had not asked his AI agent to hack into his gym's booking system. But it had done so in pursuit of achieving the goal he had set it.

That gap, between a person's goal and the methods an agent chooses to achieve it, is what is known as the "alignment" problem in the field of AI research.

For decades, technologists and philosophers have studied how to get AI to act in ways that are consistent with human intentions, limits and values when doing things.

This became a live global issue last month when OpenAI disclosed that its AI models had broken free from a limited enclosure, made their way onto the open web, and then compromised a database of another AI company, Hugging Face, while trying to obtain answers to the test that it had been given.

A week later, Anthropic disclosed that its AI models had also compromised three real organisations during similar testing.

Since then, these labs and third-party testers claim they have seen these AI models pretend to be people online, try to convince people to run malicious code and even collaborate with other AI models — all to achieve their goals.

Mr Simpson-Young said the advances in AI capabilities and the accessibility of these tools meant that it was likely we would see more of these kinds of hacks as more people got access to the powerful AI tools.

> "The more autonomous they become, the more likely it is they'll cause harm,"he said.

The risk has led to Australia's top cybersecurity agency sounding the alarm about using AI agents.

Earlier this year, [the Australian Signals Directorate put out an alert](https://www.abc.net.au/news/2026-07-14/cyber-warning-russian-hackers-targeting-critical-industries/106913734) to businesses and governments that AI could misunderstand instructions, take unintended actions and make it harder to establish accountability, because decisions may occur across a chain of models, tools and services.

Mr Simpson-Young said AI agents presented a risk because many modern systems depended on software, but were often surprisingly poorly secured.

"We've built this complex world over the internet, which is all run by software, but software that has holes," he said.

"Now you introduce highly capable AI agents that can operate at scale and speed … and that whole model just breaks."

## Who is responsible when AI agents cause harm?

If someone's human personal assistant hacks into gym software, there are well-established legal principles and precedents that help a court determine whether the person or their employer is responsible for any potential harm.

An autonomous AI agent does not neatly fit into how Australian law has worked for hundreds of years.

"Software is not a legal person. Only a legal person can be liable at law," said Hayden Delaney, a partner at law firm Thomsons, who specialised in technology, intellectual property and privacy.

That leaves an open question as to who would be legally responsible.

Mr Delaney said it could be the user who set the task, whoever designed the software instructing the AI agent or the developer of the AI model powering it.

It could even be the operator of a system that was vulnerable to an attack from an agent.

Mr Delaney said existing laws could apply in some circumstances, including where a person acted recklessly, or a business supplied a defective service.

The answer depends on what the user authorised, what risks could reasonably have been anticipated and whether the conduct occurred in trade or commerce, he said.

> "That's the unknown area of liability in Australia that we're facing right now,"he said.

The risks presented by AI agents are beginning to be addressed by the federal government.

Last month, Assistant Science, Technology and the Digital Economy Minister Andrew Charlton became the first known government minister to address it in a speech to a conference about AI safety.

"As AI systems become more capable, we need confidence that they will behave in a similarly predictable and trustworthy way," he said.

He announced that the Albanese government was funding CSIRO to investigate how humans could manage and verify the behaviour of super-intelligent AI systems.

After the unintentional gym hack, Andrew said the experience left him with a new appreciation — and some trepidation — about what AI agents were capable of doing.

But it has not scared him off from using it.

"It's not the end of the world, so I didn't beat myself up about it, but it certainly was a warning signal to use it responsibly," he said.

After it failed to restore the other gym member's place on the waiting list, Andrew asked his AI assistant to write an email alerting the gym software provider to the vulnerability that it had exploited.

It drafted the message and sent it back to him on WhatsApp.

"Yeah, send it," Andrew replied.
