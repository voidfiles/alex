# Slop Is Not Necessarily The Future | Greptile

A couple of years ago, "slop" became the popular shorthand for unwanted, mindlessly generated AI content flooding the internet including images, text, and spam. Simon Willison helped popularize the term, though it had been circulating in engineering communities in the years prior.

At Greptile, we spend a lot of time thinking about questions like: Is slop the future? Are programming best practices now a thing of the past? Will there be any reason at all for AI coding tools to write what we call good code going forward?

I want to argue that AI models will write good code because of economic incentives. Good code is cheaper to generate and maintain. Competition is high between the AI models right now, and the ones that win will help developers ship reliable features fastest, which requires simple, maintainable code. Good code will prevail, not only because we want it to (though we do!), but because economic forces demand it. Markets will not reward slop in coding, in the long-term.

## What's Happening Now?

Software development is changing fast. A prominent recent example comes from Ryan Dahl, creator of Node.js, who wrote, "The era of humans writing code is over. Disturbing for those of us who identify as SWEs, but no less true."

Meanwhile, the complexity of the average piece of software is drastically increasing. In our 2025 State of AI Coding report [1], lines of code per developer grew from 4,450 to 7,839 as AI coding tools became standard practice. Median PR size increased 33% from March to November 2025, rising from 57 to 76 lines changed. Individual file changes became 20% larger and "denser."

The stats suggest that devs are shipping more code with coding agents. While this is exciting, like many other developers I am quite alarmed by this progression. The worry is that AI slop is being shipped into production systems at an ever increasing rate leading to mass distribution of bad software. The consequences may already be visible: analysis of vendor status pages [2] shows outages have steadily increased since 2022, suggesting software is becoming more brittle. Engineers understand this, Andrej Karpathy

describes: "agents bloat abstractions, have poor code aesthetics, are very prone to copy pasting code blocks and it's a mess, but at this point I stopped fighting it too hard and just moved on."

[[3]](https://www.greptile.com#fn3)

Collectively, software engineers are cranking out code at a high quantity. And there seems to be no reason for "good" code. Most users get what they asked for, model labs get paid per token, and developers get to ship without thinking too hard.

## Why "Good Code" Will Win

In *A Philosophy of Software Design* [4], John Ousterhout argues that complexity is the #1 enemy of well-designed software. Broadly he argues that good code is:

- Simple and easy to understand
- Easy to modify

Bad code is the opposite, needs lots of context and mental bandwidth to understand and is almost impossible to modify.

This principle applies the same for AI agents. AI will write good code because it is economically advantageous to do so. Per our definition of good code, good code is easy to understand and modify from the reduced complexity. This means it requires less context to understand a relevant piece of code and fewer lines of code to be written to achieve some change. Translating this to token economics, we can clearly see the parallels: it is more token efficient to write and maintain software with good code.

By contrast, complex code doesn't scale. It requires a lot of tokens and compute, and as codebases grow, it gets exponentially more expensive.

## What This Means

We're still early in the AI coding adoption curve. As the technology and competition matures, economic forces will drive AI models toward generating good, simpler, code because it will be cheaper overall.

The world right now is focused on getting AI to work in the first place, not on optimizing its abilities. We are going through a particularly messy phase of innovation. Once AI code generation becomes ubiquitous, I believe that economic incentives will start to take effect and AI models will be forced to generate good code to stay competitive amongst software developers and companies.
