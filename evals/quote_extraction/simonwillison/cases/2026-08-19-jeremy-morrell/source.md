# Extensible Software in the age of LLMs | Jeremy Morrell

Most of the web software we interact with today is static. The developers have a limited amount of time and attention, and focus on building the features that serve the largest group of users. The top of the demand curve is well-served by existing software, but there is a long-tail of unmet needs that’s different for every user.

[Even if the developers were incredibly motivated to shove in every feature, user interfaces can only become so complex before they become unusable.](https://newsletter.getprimitive.ai/p/when-to-design-for-emergence) Every additional feature added complicates the product for every other user. If the market for that feature is small, it can actively make the product worse for every user who doesn’t need it.

With this context the rise of LLM-assisted coding has been genuinely empowering for anyone who needed something that fell into this long tail.

## Software has gotten all… squishy[#](https://jeremymorrell.dev#software-has-gotten-all-squishy)

It’s become readily apparent that LLMs are really quite excellent at building [Software for One](https://www.ajwaxman.com/writing/software-for-one). Personal apps that side-step all of the complexity and accountability of enterprise software and are custom fit for a single person’s workflow.

[Pete Koomen](https://koomen.dev/) at Y Combinator thinks there is an opportunity for what they are calling [Small Software](https://x.com/ycombinator/status/2079963726435021232). I think they are onto something.

[Pi](https://pi.dev/) is a good example of what I’m starting to think of as **LLM-native software**: a battle-tested core, but almost endlessly extensible just by asking, where users are able to share their customizations with others. **In the past year your users have suddenly acquired the ability to speak code into existence.** Most existing software can’t leverage this. Pi leans into it.

I suspect we’re going to start seeing more software following this self-extension pattern. However most of our existing examples of pluggable software are local software: AI agents, developer IDEs, mods for video games, Blender add-ons, CAD extensions. These tend to be professional tools with a high barrier to entry.

**The web is the most successful software distribution system in the world.** It shouldn’t be left behind.

My hypothesis is that **there is a new opportunity for Extensible Software on the web**. LLMs radically lower the cost of authoring extensions, and modern sandbox primitives lower the deployment cost and provide good security boundaries. We can build our app as a solid, accountable core, and allow users to safely extend it in many directions by having LLMs fill in the missing pieces. **We can give our users super powers.**

Disclosure: I currently work at Cloudflare, where high levels of exposure to [Kenton Varda](https://x.com/kentonvarda)’s writing have shaped much of my thinking here. Near the end, I’ll make the case that [Dynamic Workers](https://developers.cloudflare.com/dynamic-workers/) are a particularly good fit for this model, but I’ll cover several alternatives first.

## What would this look like?[#](https://jeremymorrell.dev#what-would-this-look-like)

A lot of web systems today rely on webhooks to allow the user to react to changes in the app. This ~kind of works, but it sets a really high bar for extension: building and operating a completely separate service plus dealing with whatever delivery issues arise.

I want to be able to hook into record updates and slide in my own logic. “When I attach this tag to a record, run my function”. “Do this action for me on a daily cron”.

Actually, I don’t want to have to think about that at all. I want to tell my read-it-later app:

- Please send every article I fave longer than 4000 words to my

  ```
  <ereader of choice>
  ```
- Look for new papers published on arxiv in

  ```
  <my specialty>
  ```

  each week, add your own summary of how it relates to my work at the top, and tag it with

  ```
  <tag>
  ```
- The default algorithm completely garbles

  ```
  <site I read frequently>
  ```

  . Pull a few examples and make a custom parser for it.

And then a robot will extrude the silly bits of code, hook them into some extensions points, and make that happen. I should also be able to share what I’ve made with anyone else who might also want the same feature.[1](https://jeremymorrell.dev#user-content-fn-participation-inequality)

Here are some more areas where I’d love to see an LLM-native extension approach.

#### AI Agents[#](https://jeremymorrell.dev#ai-agents)

Okay, this is the obvious one. [pi](https://pi.dev), [deepseek](https://www.deepseek.com/harness/en/), and [opencode](https://x.com/thdxr/status/2087945880863191162), are all experimenting in this space.

Rather than adding every new idea to its core, Pi provides stable hooks for tools, commands, events, and UI, so it can turn a request into a small TypeScript extension and reload it in place. Those extensions can then be bundled into packages that can be shared, letting the ecosystem absorb the long tail of ideas without bloating the harness itself.

However the audience of these, at least as they exist now, is fairly small. You have to be comfortable running custom software on your local machine. In corporate environments **the organization** has to be comfortable with you running software that no one has ever, or will ever, look at. Unless you sandbox Pi yourself, Pi extensions run with the same permissions as Pi itself.

Software engineers will find a way, but accountants, doctors, lawyers, and thousands of other professions deserve better tools too. They need agents that can be safely and easily tailored to their domain and their own workflows.

If we’re going to get more people using agents, that doesn’t mean making them software developers. It means making the software fit their needs.

#### Internal Corporate Platform[#](https://jeremymorrell.dev#internal-corporate-platform)

All companies end up with tons of data. Employees need to view it, query it, investigate it, correlate it with this other data in this other system, find customers experiencing

```
<problem x>
```

, find customers about to churn, and a million more things.

A lot of companies are experimenting with allowing AI-enthusiast employees to vibe code their own tooling, maybe deploy it to a PaaS. This is directionally correct, but creates a bunch of downstream problems. Once you have hundreds or thousands of these apps, how do you maintain them? How do they get access to the data that they need? How do they get access to **only the data that they need**? How can we audit what this software is doing? If we’re relying on access tokens, what are their scopes? Who rotates them? How do we make sure that we’re not logging out customer information to a third-party? How do we make sure we’re not violating GDPR?

Or a million other compliance and security things that real businesses need to worry themselves about.

What if we gave them a place to deploy code where there are no auth tokens that can leak? Where data access is handled by an internal platform team that can ensure all of the compliance boxes are checked? Give them the space to build their own automations or custom views, but safely.[2](https://jeremymorrell.dev#user-content-fn-vibe-coding-platforms)

Spoiler: This is basically [Cloudflare OS](https://github.com/cloudflare/cloudflare-os).

#### Support Platform[#](https://jeremymorrell.dev#support-platform)

I’ve spent a lot of my career handling tricky support tickets. Inevitably I end up digging through dashboards, searching logs, pulling data from a million different places. Let me create extensions that surface data for the user that opened the ticket from my particular system into the support interface. Give me hooks so I can kick off agents to do the first round of investigation for me, before I even look at it. If there are common tasks that I need to do like “reset specific quota X” let me add a button to my view that can do that.

Then also let me share these with my team so we can all help each other.

#### Observability Platform[#](https://jeremymorrell.dev#observability-platform)

A lot of Observability tooling has converged towards the same feature set: a way to search your logs with the little bar graph on top. A trace waterfall view for viewing individual traces. Customizable metrics dashboards. Maybe a service map. A few are experimenting [with new visualizations](https://embrace.io/), especially with [the rise of agents](https://www.honeycomb.io/blog/agent-timeline-flight-recorder-for-your-ai-agents).

The venerable trace waterfall diagram is very useful for systems that are shaped as request / response, where you mainly care about latency and success rate. A lot of us are finding ourselves with systems that are a bit more… stateful… or dynamic. Modern apps are running non-deterministic agents or durable workflow engines where a single action might take hours or days. Trace spans are a great source-of-truth to build upon, but let me experiment with my own visualizations (or install someone else’s).[3](https://jeremymorrell.dev#user-content-fn-frontend-sandboxing)

Beyond pretty things I can look at, let me inject my own logic:

- arbitrary transforms for data on ingestion
- have alarms kick off my own scripts: deterministic code or my own agent
- give me options to run my own code at times of highest risk: deploys or feature flag rollouts
- if I have a special

  ```
  MyResourceID
  ```

  in my logs, let me turn that into a link that goes straight to that resource on another platform

## Extensible software on the web is… harder[#](https://jeremymorrell.dev#extensible-software-on-the-web-is-harder)

I just made all of that sound easy. It’s nothing of the sort.

I’m a big fan of Obsidian, both as a tool I use every day and as a piece of software.

It seems like a basic markdown editor, but with a few clicks you can extend it to do just about anything: [track your tasks in a kanban board](https://publish.obsidian.md/kanban/Obsidian+Kanban+Plugin) or [turn your notes into a database](https://github.com/blacksmithgu/obsidian-dataview). Want to shove all your notes into a vector database for semantic search? [Go for it](https://motherduck.com/blog/obsidian-rag-duckdb-motherduck/)! And if you want to go further, the underlying web UI primitives are easily hackable.

However that power comes with a cost: Obsidian’s extension model requires you to trust every plugin you install. [A plugin can basically do anything](https://cyber.netsecops.io/articles/obsidian-plugin-abused-in-campaign-to-deploy-phantom-pulse-rat/). Obsidian fights this security challenge with [automated and manual review](https://obsidian.md/blog/future-of-plugins/) and by verifying plugin authors.

For a notes app this is likely the right tradeoff. It works because the stakes are low and the community is relatively small. But this model falls apart the moment you want the same level of extensibility in software holding other people’s data: customer records, financial transactions, private messages. Extensibility and web services have always been a challenge.

Executing arbitrary code is rife with security and abuse challenges. An incomplete list:

- Errors or infinite loops in the user’s code should never take down your service
- With access to keys, customer extensions can forward them to a third party
- Likewise if you expose sensitive data, make sure it can’t be exfiltrated
- Make sure this system can’t be abused to do a Denial of Service attack
- Make sure the user can’t accidentally Denial of Service you
- Protect against [Spectre](https://meltdownattack.com/)attacks
- If people can use free compute to mine crypto on your dime, they will
- and many more…

## But surely someone has done this?[#](https://jeremymorrell.dev#but-surely-someone-has-done-this)

Before we write this off as infeasible, there is a clear example where this kind of extensibility on the web has worked at immense scale: Salesforce.

Yes, that Salesforce. [And they’ve been doing it since 2007](https://www.eweek.com/enterprise-apps/salesforce-com-issues-summer-07-release-apex-code/). (As a point of reference, AWS S3 and EC2 were launched [in 2006](https://en.wikipedia.org/wiki/Timeline_of_Amazon_Web_Services).)

Ask most technologists what Salesforce is and you’ll either get a blank stare or maybe something to the effect of “Aren’t they a CRM?”. However it’s more accurate to describe Salesforce as a massive multi-tenant programmable platform. In the nascent cloud era this cut against the grain: no containers, and forcing people into writing this weird, custom [Java-like language, Apex](https://developer.salesforce.com/docs/atlas.en-us.apexcode.meta/apexcode/apex_intro_what_is_apex.htm).

However with the rise of serverless, the platform starts to look a lot more familiar. Consider some examples:

If I need to expose a custom endpoint, I can do so with a few lines of code. The platform handles routing, authentication, tenant isolation, execution. There is no webserver to deploy. Squint and [you can see it as a precursor to modern serverless](https://developers.cloudflare.com/workers/examples/return-json/).

```
```
@RestResource(urlMapping='/customer-health')
global with sharing class CustomerHealthApi {
    @HttpGet
    global static Account getCustomer() {
        String accountId =
            RestContext.request.params.get('accountId');

        return [
            SELECT Id, Name, Health_Score__c, Renewal_Date__c
            FROM Account
            WHERE Id = :accountId
            WITH USER_MODE
            LIMIT 1
        ];
    }
}
```
```

```
```
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const accountId = new URL(request.url).searchParams.get("accountId");

    const account = await env.ACCOUNTS.prepare(`
      SELECT id, name, health_score, renewal_date
      FROM accounts
      WHERE id = ?
      LIMIT 1
    `)
      .bind(accountId)
      .first();

    return Response.json(account);
  },
} satisfies ExportedHandler<Env>;
```
```

Or what about running custom logic [on a schedule](https://developers.cloudflare.com/workers/examples/cron-trigger/)?:

```
```
public class RenewalScanner implements Schedulable {
    public void execute(SchedulableContext context) {
        List<Account> accounts = [
            SELECT Id, Needs_Attention__c
            FROM Account
            WHERE Renewal_Date__c = NEXT_N_DAYS:30
            WITH USER_MODE
        ];

        for (Account account : accounts) {
            account.Needs_Attention__c = true;
        }

        update as user accounts;
    }
}

// Schedule it to run daily at 2 a.m.:
System.schedule(
  'Check upcoming renewals',
  '0 0 2 * * ?',
  new RenewalScanner()
);
```
```

```
```
export default {
  async scheduled(controller: ScheduledController, env: Env) {
    await env.ACCOUNTS.prepare(`
      UPDATE accounts
      SET needs_attention = TRUE
      WHERE renewal_date BETWEEN date('now')
        AND date('now', '+30 days')
    `).run();
  },
} satisfies ExportedHandler<Env>;
```
```

```
```
{
  "name": "renewal-scanner",
  /* ... */
  "triggers": {
    "crons": ["0 2 * * *"]
  },
}
```
```

There are also higher-level primitives so you can point-and-click your way into a custom application, but at its heart Salesforce is safely running your custom logic directly in response to app events, within transactions, and allowing you to encode the particulars of your business into their app.

Two decades ago Salesforce didn’t have a ton of options for a way to cheaply run sandboxed code on behalf of their users, so they built out a compiler, type system, runtime, standard library, debugger, integrated SQL into the language, lots of fancy database tricks and heaps more, and then built out a whole educational ecosystem. The problems it solved for businesses were valuable enough to justify hiring humans who specialized in their particular development platform.

We can be inspired by what they’ve done without copying it exactly. We have a lot more options in 2026, so let’s look at what the technical requirements are for building something like this, and then what technologies might fit.

## A new primitive[#](https://jeremymorrell.dev#a-new-primitive)

We need a primitive to build this extensibility around. In order to make it work, it needs to have a couple of properties.

#### ~~Cheap~~ Economical to run[#](https://jeremymorrell.dev#cheap-economical-to-run)

If you are going to have thousands or millions of users running snippets of custom code, the idea of spinning up a custom-container-per-user is a non-starter. It needs to cost ~$0 when it’s not being executed, and each execution ideally needs to be tiny-fractions-of-a-penny cheap.

Add to that cost to build or compile, store the built artifacts, collect logs, and more. Especially with RAM prices in 2026, how much memory overhead is required to serve a request will largely determine how many users you can pack onto a single machine.

#### Fast cold starts[#](https://jeremymorrell.dev#fast-cold-starts)

We all want our web services to be fast, so if we’re running user code as part of the critical path of responding to a request, we can’t wait a minute plus for a container to spin up. Ideally a cold start is measured in single-digit milliseconds.

If you are only offering extensions that respond to events or run on a schedule you can likely afford higher startup times.

#### Control over limits[#](https://jeremymorrell.dev#control-over-limits)

Users of platforms do all sorts of weird, edge-case things. One of my favorite stories from an engineer at Heroku was that someone had published a very popular getting-started guide that had the user deploy the following Python app:

```
```
while True:
   print("hello world!");
```
```

From the system’s perspective you have a brand-new app suddenly come into existence and immediately start
spewing millions of lines of logs per second that will never stop, and the user expects something
reasonable to happen when they run the

```
tail
```

command.

To protect your system you need to be able to enforce limits on basically everything: CPU, memory, number and size of network requests, response size, log volume and rate, and much more.

#### Solid isolation boundary[#](https://jeremymorrell.dev#solid-isolation-boundary)

I mean this in both the fault isolation and security isolation senses. No matter what the user does: crashes, runs an infinite loop, allocates memory as fast as possible, it should have no effect on any other user.

And actively malicious code must not be able to escape or inspect other tenants. This includes speculative execution attacks like [Spectre](https://en.wikipedia.org/wiki/Spectre_(security_vulnerability)).

#### Allow the code to take actions (safely)[#](https://jeremymorrell.dev#allow-the-code-to-take-actions-safely)

Custom code that can’t affect anything is useless, so we need some controlled way for user code to interact with the rest of the world. In the simplest case you can model things as a pure function. The user’s code receives some data as input and can respond with an answer. If there is no I/O allowed, and a constrained output, this is quite safe, if limiting.

```
```
export default function shouldWeOrderPizzaTonight(data: Input): boolean {
  // consider the options very carefully
  const haveFoodAtHome = data.fridge.hasIngredients;
  const haveEnergy = data.body.checkCapacity;
  const haveTime = !data.schedule.isTight;
  
  // return haveFoodAtHome && haveEnergy && haveTime;
  // we don't believe in data-driven decision making in this household
  return true;
}
```
```

If you need to expose more to the user, then things get a little more tricky. When we want our own code to call an API, we typically add some sort of API key that we can attach to our requests:

```
```
const response = await fetch(api, {
  headers: {
    Authorization: `Bearer ${env.API_KEY}`,
  },
});
```
```

But this kind of flexibility is dangerous! Malicious code can immediately leak that data by

```
POST
```

ing it to a
third-party. Even exposing raw

```
fetch
```

means that the user can now use your infrastructure to DoS someone if they want.

The most common solution for this today is adopting a proxy. The user is given an opaque token that is meaningful only
to the proxy. The proxy validates the request, and then replaces the opaque token with the real credential, before
forwarding the request to the destination. The proxy can also
enforce an allowlist of possible destinations and rate-limits on requests. This is strictly better than raw

```
fetch
```

,
but still has some problems.

```
```
const response = await fetch(apiViaProxy, {
  headers: {
    Authorization: `Bearer REPLACE_THIS_WITH_MY_API_KEY_IN_PROXY`,
  },
});
```
```

You may want to restrict what the code can do to only a subset of what the API allows, which requires very
fine-grained authentication that most APIs do not offer. [There can be pretty dire consequences if that API
provides too much power, or is exploitable in ways you cannot foresee.](https://www.youtube.com/watch?v=87DyyMV0kCY)

Even if the service provides fine-grained permissions, like the ability to read your email, that may still be far more access than you want to give the code. If you want to give the code only access to one specific email, there’s generally no token you can generate that allows only this.

You can try to enforce that in a proxy, but now you are tasked with filtering out all requests that don’t match some narrow set of criteria, and keeping that up-to-date as the backing API evolves. Our proxy code quickly becomes very complicated. It’s difficult to anticipate everything a user might do here. Testing this logic and making sure it’s bulletproof is challenging.

```
```
async function proxyFetch(url: URL, headers: Headers) {
  const opaqueToken = headers
    .get("Authorization")
    ?.replace(/^Bearer\s+/i, "");

  const grant = await parseToken(opaqueToken);

  if (!grant || grant.action !== "read-email") {
    throw new Error("Forbidden");
  }

  const allowedPath = 
    `/email/v1/users/messages/${encodeURIComponent(grant.messageId)}`;

  if (
    url.origin !== "https://email.service.com" ||
    url.pathname !== allowedPath
  ) {
    throw new Error("Forbidden");
  }

  const newHeaders = new Headers();

  // Forward only explicitly permitted headers.
  for (const name of ["accept", "if-none-match"]) {
    const value = headers.get(name);

    if (value !== null) {
      newHeaders.set(name, value);
    }
  }

  // Replace the opaque token with the real credential.
  newHeaders.set("Authorization", `Bearer ${EMAIL_API_KEY}`);

  return fetch(url, { headers: newHeaders });
}
```
```

And this is the filtering logic for just one operation on just one endpoint. In general, starting with a lot of power and then trying to restrict it precisely is a hard problem.

A better way is to hand the untrusted code a [narrow capability](https://en.wikipedia.org/wiki/Object-capability_model).
At a high level you can think of a capability as a reference to a specific function, such as one for fetching one approved-in-advance email:

```
```
// Trusted host code
const getApprovedEmail = () => fetchEmailById(123, auth);

// Untrusted extension code
export default async function doSomethingWithAnEmail(
  { getApprovedEmail }: Capabilities,
) {
  const email = await getApprovedEmail();
  // do something with the email
}
```
```

If we remove ambient I/O, **the code can only take actions via the references it has been passed**.
This pattern is **much** easier to reason about. We don’t have to muck around with complicated
proxy logic. The API credential is never exposed to the untrusted code at all. And without some other
outbound capability, there’s no way to leak data.[4](https://jeremymorrell.dev#user-content-fn-cloudflare-bindings)

As a bonus, generating logic from a TypeScript definition of capabilities is much easier and token-efficient for an LLM than handing it a pile of OpenAPI JSON definitions.

If you are familiar with [IFTTT](https://ifttt.com/), it doesn’t give you a Twitter API key, it gives you
 [twitter.post\_new\_tweet()](https://ifttt.com/twitter/actions/post_new_tweet). You don’t get a full email
client, you get

[.](https://ifttt.com/email/actions/send_me_email)

```
email.send_me_email
```

This is the shape we generally want for safe extensible software.

## What technology fits?[#](https://jeremymorrell.dev#what-technology-fits)

The more agent-brained among you have noticed by now that these are the same properties that you are looking for from an agent execution platform. That’s not a coincidence! This is essentially the same problem: how can you run logic on behalf of a user that you cannot trust.

The solution space has a number of options:

#### Interpreter[#](https://jeremymorrell.dev#interpreter)

Building their own language worked for Salesforce twenty years ago, and [this pattern still
works today](https://docs.langchain.com/oss/python/deepagents/interpreters).

You can use an off-the-shelf embeddable interpreter like [Lua](https://www.lua.org/) or
[QuickJS](https://bellard.org/quickjs/) or [roll your own](https://x.com/huntlovell/status/2071985800909410797).

#### V8 Isolates[#](https://jeremymorrell.dev#v8-isolates)

If you take the interpreter approach to it’s logical conclusion, you’ll eventually end up wanting to move to bytecode, and adding a JIT, and…

Jumping straight to V8 saves you the time. Google has dumped enormous amounts of money and developer time into hardening the V8 JavaScript
engine. Cloudflare uses [v8 isolates](https://developers.cloudflare.com/workers/reference/how-workers-works/)
as its isolation boundary for Workers, but it’s not the only option in this space.

- Cloudflare has [Dynamic Workers](https://developers.cloudflare.com/dynamic-workers/)
- celld has (implemented some parts of) [Dynamic Workers](https://celld.dev/docs/cloudflare-compat/#dynamic-worker-loading-code-mode)
- Node has

  ```
  isolated-vm
  ```
- Rivet has

  ```
  secure-exec
  ```

#### MicroVMs[#](https://jeremymorrell.dev#microvms)

Full VMs emulate a lot of virtual hardware: USB, graphics, disks, etc, which is what allows you to run full desktop environments in them, but that comes at a cost. Millions of lines of code and complexity that needs to boot up and takes up resources.

MicroVMs strip that back to the bone, running very constrained operating systems, but the payoff is that they can start in under a second and have a very small memory overhead with strong isolation boundary.

MicroVMs have more overhead than the other options, but have some distinct benefits:

- POSIX
- potential to utilize a lot of CPU and RAM
- full OS capable of running binaries

If you mainly want to allow the user to run some bit of logic, call some API endpoints, run a workflow, then the overhead of this approach might make it overkill. However even if you go with something like V8 isolates or WASM as your isolation primitive, microVMs could still be quite useful for authoring, compiling / bundling, and testing user extensions.

This is a **very** hot space with a lot of options:

- [Firecracker](https://github.com/firecracker-microvm/firecracker)
- ```
  libkrun
  ```
- [AWS Lambda MicroVMs](https://aws.amazon.com/lambda/lambda-microvms/)
- .

  ```
  @deno/sandbox
  ```
- [smolvm](https://smolmachines.com/)
- [Tensorlake](https://www.tensorlake.ai/)
- [Daytona](https://www.daytona.io/)
- Probably a million more…

#### WASM + WASI[#](https://jeremymorrell.dev#wasm--wasi)

WebAssembly starts out with a blank slate. The code can run, allocate memory, but there are no built-in modules for making an HTTP request, or reading an environment variable. This makes it an attractive candidate from a security perspective!

[WASI](https://wasi.dev/) defines a standard interface where the host can define the capabilities that
get passed to the untrusted WASM code.

By integrating at this lower level, you can get a lot of potential performance and allow users to write in any language that can compile to WebAssembly, but the tool chain grows significantly in complexity.

You can also run WebAssembly within a V8 isolate or [microVM](https://opensource.microsoft.com/blog/2025/03/26/hyperlight-wasm-fast-secure-and-os-free/). None of these options are mutually exclusive.

If the isolation primitive does not provide its own capability model, it’s still a useful way of thinking
through how you expose functionality. A proxy can work in some cases, but you should also consider using
an Object Capability protocol like [Cap’n Web](https://github.com/cloudflare/capnweb) with any of these
primitives.

However there’s one solution here that I want to highlight in particular…

## Cloudflare’s Dynamic Workers[#](https://jeremymorrell.dev#cloudflares-dynamic-workers)

Cloudflare’s [Dynamic Workers](https://developers.cloudflare.com/dynamic-workers/) were built with exactly this kind
of use in mind. The marketing for them has (understandably) been focused on [code mode](https://blog.cloudflare.com/code-mode/) and agent use-cases, but IMO it’s much broader than that.

Beyond meeting the criteria I proposed above, they are the closest thing to a production-ready out-of-the-box framework for building extensible web apps that I’ve been able to find in 2026. (But I bet there will be more soon)

There are a handful of things that they provide that you’ll need to build out yourself with other solutions:

#### Observability[#](https://jeremymorrell.dev#observability)

(My day job and personal soapbox)

Both you and your users need visibility into what their code is doing. Cloudflare Workers [have OpenTelemetry
tracing built into the runtime itself](https://blog.cloudflare.com/workers-tracing-now-in-open-beta/) and have
[first-class primitives](https://developers.cloudflare.com/workers/observability/logs/tail-workers/) that allow
you a lot of control over emitted telemetry.

#### Multi-tenant data storage[#](https://jeremymorrell.dev#multi-tenant-data-storage)

While not every extension system needs users to be able to store their own data, this gives users a lot more flexibility.

Give them their very own SQLite database with [Durable Object facets](https://blog.cloudflare.com/durable-object-facets-dynamic-workers/). [Or give them their own R2 bucket](https://developers.cloudflare.com/cloudflare-for-platforms/workers-for-platforms/).

#### Durable Execution[#](https://jeremymorrell.dev#durable-execution)

The rise of [Temporal](https://temporal.io/) et al has shown that a lot of problems benefit from Durable Execution. [Dynamic Workflows](https://blog.cloudflare.com/dynamic-workflows/) lets users to take actions over minutes or days, with appropriate retries and backoff.

#### Source Control[#](https://jeremymorrell.dev#source-control)

Users probably need to version and iterate on their extensions, and you can’t expect that everyone uses GitHub. [Build source control into your product](https://www.cloudflare.com/products/artifacts/).

#### Hosted LLMs[#](https://jeremymorrell.dev#hosted-llms)

Users can use LLMs to help draft their extensions, but you can also expose LLMs through [Workers AI](https://www.cloudflare.com/products/workers-ai/) so users can use them in their extensions (with appropriate token budgets and rate limits).

```
```
export async function analyzeArticle(env: Env, article: Article) {
  return result = await env.AI.run(
    messages: [
      {
        role: "system",
        content: "Decide whether the supplied article talks about cute kittens.",
      },
      {
        role: "user",
        content: article.text,
      },
    ],
  )
}
```
```

#### Self-hosting JavaScript Tooling[#](https://jeremymorrell.dev#self-hosting-javascript-tooling)

A lot of JavaScript tooling is itself written in JavaScript, which means that building and testing extension code might not need a separate container or VM.

```
```
import { transform } from 'sucrase';

export function transpileUserCode(source: string): TranspileResult {
  try {
    const result = transform(source, {
      transforms: ['typescript'],
      disableESTransforms: true
    });
    return { type: 'success', code: result.code };
  } catch (err) {
    return { type: 'failure', error: String(err) } };
  }
}
```
```

## Demo Time[#](https://jeremymorrell.dev#demo-time)

As I was writing this post I thought “What if I turned my static blog into the world’s
smallest vibe-coding platform?”[5](https://jeremymorrell.dev#user-content-fn-byo-vibes)

I wanted to include a guide to working with Dynamic Workers and some cool demos, but
this blog post is already way too long. I split that out into a guide to [Working
with Dynamic Workers](https://jeremymorrell.dev/blog/working-with-dynamic-workers) but still wanted to embed
the final demos here.

The demo’s harness is based around the idea of a customizable scraper. Given a URL, it will fetch the contents (unless they block Cloudflare), and pass those contents and a few utilities to the user’s code. See the guide for a full explanation.

All of the examples run on Cloudflare Workers, and the source is editable. Modify any of them to run your own script, or if you want to write your own choose “Write your own” and there’s an LLM prompt to get you started.

Each example runs through the same harness, but exercises a different combination
of libraries and capabilities. Choose one, pick a suggested URL, or your own, and hit **Run**.

## Here be dragons[#](https://jeremymorrell.dev#here-be-dragons)

One last thought.

I’ve worked at platforms for almost a decade. I don’t mean to make “turn your app into a platform” sound easy. Platforms are hard: hard to design, hard to run, hard to debug.

Exposing APIs to customers means a lot of upfront thought, and long-term support (though maybe LLMs can make this a lot easier?).

But they are also really fun, both as a user and a creator. You can be truly surprised by the creativity of your users as they do things that you never considered or would have even thought possible.

Platforms are hard, but it’s worth it.

## Appendix[#](https://jeremymorrell.dev#appendix)

Some things that were influential in drafting this blog post:

- [Kenton Varda](https://x.com/KentonVarda)’s many writings and talks
- [Cloudflare OS](https://os.cloudflare.app/)
- [Ink and Switch](https://www.inkandswitch.com/)’s[Malleable Software](https://www.inkandswitch.com/essay/malleable-software/)
- [Andy Matuschak](https://andymatuschak.org/)’s[Apps and programming: two accidental tyrannies](https://andymatuschak.org/tat/)

## Footnotes[#](https://jeremymorrell.dev#footnote-label)

- [1.](https://jeremymorrell.dev#user-content-fnref-participation-inequality)

  I suspect that even in a fully LLM-accelerated world

  [participation equality](https://www.nngroup.com/articles/participation-inequality/)is still going to be A Thing. A small percentage will author most of the extensions in any given ecosystem, no matter how easy we make it.[↩](https://jeremymorrell.dev#user-content-fnref-participation-inequality)
- [2.](https://jeremymorrell.dev#user-content-fnref-vibe-coding-platforms)

  If you squint, vibe coding platforms are kind of a generic version of this, except instead of providing custom functionality for your organization, they provide generic data storage and hosting. I expect they will start to add this kind of customized hosted access as they start selling to Enterprise.

  [↩](https://jeremymorrell.dev#user-content-fnref-vibe-coding-platforms)
- [3.](https://jeremymorrell.dev#user-content-fnref-frontend-sandboxing)

  This completely glosses over a need to sandbox UI on the client side where custom code can access potentially sensitive data.

  [That topic deserves its own post.](https://github.com/endojs/endo/tree/master/packages/ses). Or point your robot atand ask it how it’s done there.

  ```
  cloudflare-os
  ```

  [↩](https://jeremymorrell.dev#user-content-fnref-frontend-sandboxing)
- [4.](https://jeremymorrell.dev#user-content-fnref-cloudflare-bindings)

  If you’re familiar with Workers, you might be thinking “this looks a lot like bindings…”. Yes! Bindings and Service Workers work on an

  [Object Capability RPC system](https://developers.cloudflare.com/workers/runtime-apis/rpc/). You can think of exposing capabilities to users as generating bindings for your particular service.[↩](https://jeremymorrell.dev#user-content-fnref-cloudflare-bindings)
- [5.](https://jeremymorrell.dev#user-content-fnref-byo-vibes)

  You’ll have to bring your own vibes though. I decided “expose free LLM usage to the internet” was probably not in my best financial interest.

  [↩](https://jeremymorrell.dev#user-content-fnref-byo-vibes)
