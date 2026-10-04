# Index cards

I find questions about writers’ tools both fascinating and repulsive: fascinating because learning about the habits and techniques of people whose work you admire is endlessly interesting, and occasionally even imparts useful knowledge. (If John McPhee [swears by index cards as a method for determining a story’s structure](http://www.newyorker.com/reporting/2013/01/14/130114fa_fact_mcphee), you ought to at least give it a try.) But discussions of tools also tend to be far too precious, leading people to imagine that if they cannot wake early and slip out to their private writer’s cabin, then they cannot possibly write and so ought to stay in bed. The fetishization of tools is a mechanism for procrastination and should be rejected as such.

But assuming we recognize that risk and take pains to avoid it, talking about our tools can be instructive. Routines and tools *do* matter—not only for writers but for any skill or trade. A good chef’s knife makes a good cook better, while a dull blade will limit her skills. A cook with a mandoline will have opportunities that one without will lack. It’s just as ignorant to say that tools don’t matter at all as it is to pronounce them magical.

Late last year, [Jeremy Keith wrote](http://adactio.com/journal/6620/) about what it means to publish online today:

> Publishing on your own website is still just too damn geeky. The siren-call of the silos is backed up with genuinely powerful, easy to use, well-designed tools. I don’t know if independent publishing can ever compete with that.

The thing is, I *like* the geeky parts of publishing. That’s part of why I publish anything at all. Writing here was never just about sharing my writing but also about building systems for that writing: systems that could enable a particular kind of writing, which may even be unique to me (or as unique as anything gets, anyway). And so the process for how that writing comes together, and the tools I use to build it, are as important to me as the rhythm of any particular sentence.

I am similarly aligned with Jeremy on another point: that of [preservation](https://aworkinglibrary.com/writing/forever/). Independent publishing on the web benefits by being free of concerns about what will happen to your work. No one owns this domain but me, and no one but me can take it down. I will not wake up one morning to discover that my service has been “sunsetted” and I have some days or weeks to export my data (if I have that at all). These URLs will never break. If nothing else, that security is a compelling reason to publish on your own site, never mind how geeky it is.

But preservation doesn’t only depend on control over a space: it also depends on the format of the stuff you’re trying to preserve. I’ve always published to my own domain; but for years that writing was preserved in the form of a database—something that needed to be manipulated by another tool to be useful or readable. Increasingly, that database felt inaccessible to me, like a mysterious black box I couldn’t see into. I didn’t feel confident that, some years or decades from now, I would be able to access or read that writing in that form.

But what format can I reliably expect to find useful in five or ten or more years? Well, text. Or HTML, which is just text with some structure. I’m pretty optimistic that HTML will live another few decades at least, but even if it didn’t, HTML is helpfully both machine *and* human readable: absent a browser to interpret HTML, I can still read it with my own two, bespectacled eyes. (Or, should those eyes fail me, with any number of text-to-speech tools.)

The question then becomes how to best publish a collection of text files. Enter [Jekyll](http://jekyllrb.com), one of many static site generators and maybe the most popular. Static site generators take a collection of files and generate all the necessary pages for a website, which can then be shared on any web server (in my case, Amazon’s S3). In this way, they resemble publishing systems from the early days of the web, when “publishing” largely meant uploading new files via FTP. Generators eliminate some of the tedium of those old-school methods, while preserving the overall spirit.

With Jekyll, instead of a database, I have a folder full of text files. Here’s what a post for the book  *Hild* looks like, for example:

```
```
---
layout: book
title: Hild
subtitle: A Novel
author: Nicola Griffith
amazon-url: http://www.amazon.com/dp/0374280878
publisher: Farrar, Straus and Giroux
copyright: 2013
cover: /img/griffith-hild.jpg
excerpt: From the scant historical record of Hild of Whitby, Griffith spins an extraordinary story of a girl who learns to navigate the world of kings and thegns.
permalink: /reading/hild
---

From the scant historical record of Hild of Whitby, Griffith spins an extraordinary story of a girl who learns to navigate the world of kings and thegns. Hild is fierce and clever...
```
```

The stuff up at the top is a [YAML](http://www.yaml.org) block. YAML is defined as a “a human friendly data serialization standard.” Another way to define it is a readable, plain-text method for indicating metadata. Even if you’ve never seen YAML before, you can probably figure this out at a glance. At the top,

```
layout: book
```

signals to Jekyll that this post uses the layout (or template) called “book.” (This site has three principle layouts—book, essay, and note—for each of the three kinds of posts.) Next is the

```
title
```

, which in this case is both the title of the book and the title of the post. Following that are

```
subtitle
```

,

```
author
```

,

```
amazon-url
```

,

```
publisher
```

,

```
copyright
```

, and

```
excerpt
```

, all of which are self explanatory.

What’s different about this method versus other types of systems? Foremost, I’m working in simple plain text files in order to write and publish. I can use any text editor I want. The act of creating metadata is in close proximity to the act of writing—I just have to type the relevant data, using a vocabulary I’ve defined and can modify when I choose. The posts themselves are written in Markdown, which is just shorthand for HTML, and I can include regular old HTML when I need it. That means I don’t have to learn a new system or its quirks to write; I can lean on skills I already have—indeed, skills which are native to the web itself, rather than quirks of a particular program.

And the end result is a collection of files which needs no further mediation to be read.

It should be noted that this is a hell of a lot more work than, say, setting up a new WordPress site, and leans on a workflow that draws heavily from web development. In order to publish a new post I must:

- Create a text file with the content of the post and the appropriate YAML frontmatter.
- Run my local server to build the site and review the post. (In practice, that means I type

  ```
  jekyll serve
  ```

  from the command line and then point my browser at

  ```
  localhost:4000
  ```

  .)
- Commit the new files to the repository. (The entire source of the site, including all the text files, images, styles, and scripts, live in a GitHub repo. This is not strictly necessary, but it is a good idea to manage the site’s assets with version control, so you can roll back if need be.)
- Deploy the new files to S3 via another command line tool. (I could move files to S3—or any other web server—via FTP, but I found this to be easier.)

In order to accomplish all this, I need to be comfortable both with GitHub and the command line. To get things up and running, I also needed to install Ruby plus several Ruby gems, modify multiple configuration files, set up an Amazon S3 bucket for static website hosting, and develop the layout files, not to mention all of the HTML, CSS, and JS that’s required for what is (at the end of the day) a relatively simple site.

If my goal was just to write and publish, this would be preposterous. There are far easier ways to go about that—and many of them are exceptionally well-designed, as Jeremy wisely points out. But that’s not my only goal: I also want to design the system my writing inhabits, and to maintain a proximity to the development process which can inform how that system evolves. That is, I want to be as close as possible to the forms, mechanisms, and methods by which my words are published.

Because this site isn’t just a collection of words: it’s also a visual design, an evolving taxonomy, and a structure for relating books and ideas. The writing is not inseparable from that fact.

There are many advantages to platforms, like WordPress and its ilk, that handle this kind of work for you (not the least of which is you don’t need years of experience as a web developer to prepare for it). But they also restrict your ability to change and experiment with the structure and organization of your writing. They imagine a line separates the authoring and editorial work from the design and production. [I don’t much care for that line.](http://frankchimero.com/talks/designing-in-the-borderlands/transcript/) And I don’t want anything to prevent me from crossing it.

[Jeremy Keith](http://adactio.com/journal/6786/), again:

> These days, browsers don’t like to expose “view source” as easily as they once did. It’s hidden amongst the developer tools. There’s an assumption there that it’s not intended for regular users.

Fuck that. I’m more of an editor than a developer any day, but I’ll be damned if I’m going to cede that territory. I don’t want to pour my words into a box, the parameters of which someone else decides (and obscures). I want to make the box, too. And remake it. And, hell, break it from time to time. It’s mine to break.

That’s what I’m trying to do here. And I’m hopeful that, over time, it will prove to be at least as instructive as John McPhee’s index cards.

I’m grateful for excellent feedback on this essay from [David Yee](http://tangentialism.com), [David Sleight](http://stuntbox.com), [Allen Tan](http://tanmade.com), [Josh Stewart](https://twitter.com/josh_stewart), and [Nicole Fenton](http://www.nicolefenton.com).
