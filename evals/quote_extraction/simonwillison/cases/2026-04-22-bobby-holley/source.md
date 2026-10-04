# The zero-days are numbered  | The Mozilla Blog

# The zero-days are numbered

Since February, the Firefox team has been working around the clock using frontier AI models to find and fix latent security vulnerabilities in the browser. We [wrote previously](https://blog.mozilla.org/en/firefox/hardening-firefox-anthropic-red-team/) about our collaboration with Anthropic to scan Firefox with Opus 4.6, which led to fixes for 22 security-sensitive bugs in Firefox 148.

As part of our continued collaboration with Anthropic, we had the opportunity to apply an early version of Claude Mythos Preview to Firefox. This week’s release of Firefox 150 includes fixes for 271 vulnerabilities identified during this initial evaluation.

As these capabilities reach the hands of more defenders, many other teams are now experiencing the same vertigo we did when the findings first came into focus. For a hardened target, just one such bug would have been red-alert in 2025, and so many at once makes you stop to wonder whether it’s even possible to keep up.

Our experience is a hopeful one for teams who shake off the vertigo and get to work. You may need to reprioritize everything else to bring relentless and single-minded focus to the task, but there is light at the end of the tunnel. We are extremely proud of how our team rose to meet this challenge, and others will too. Our work isn’t finished, but we’ve turned the corner and can glimpse a future much better than just keeping up. **Defenders finally have a chance to win, decisively.**

Until now, the industry has largely fought security to a draw. Vendors of critical internet-exposed software like Firefox take security extremely seriously and have teams of people who get out of bed every morning thinking about how to keep users safe. Nevertheless, we’ve all long quietly acknowledged that bringing exploits to zero was an unrealistic goal. Instead, we aimed to make them so expensive that only actors with functionally unlimited budgets can afford them, and that the cost of burning such an expensive asset disincentivizes those actors against casual use.

This is because security to date has been offensively-dominant: the attack surface isn’t infinite, but it’s large enough to be difficult to defend comprehensively with the tools we’ve had available. This gives attackers an asymmetric advantage, since they only need to find one chink in the armor.

We use *defense-in-depth* to apply multiple layers of overlapping defenses, but no layer is bulletproof. Firefox runs each website in a separate process sandbox, but attackers try to combine bugs in the rendering code with bugs in the sandbox to escape to a more privileged context. We’ve led the industry in building and adopting Rust, but we still can’t afford to stop everything to rewrite decades of C++ code, especially since Rust only mitigates certain (very common) classes of vulnerabilities.

We pair defense-in-depth engineering with an internal red team tasked with staying on the leading edge of automated analysis techniques. Until recently, these have largely been dynamic analysis techniques like fuzzing. Fuzzing is quite fruitful in practice, but some parts of the code are harder to fuzz than others, leading to uneven coverage.

Elite security researchers find bugs that fuzzers can’t largely by reasoning through the source code. This is effective, but time-consuming and bottlenecked on scarce human expertise. Computers were completely incapable of doing this a few months ago, and now they excel at it. We have many years of experience picking apart the work of the world’s best security researchers, and Mythos Preview is every bit as capable. So far we’ve found no category or complexity of vulnerability that humans can find that this model can’t.

This can feel terrifying in the immediate term, but it’s ultimately great news for defenders. A gap between machine-discoverable and human-discoverable bugs favors the attacker, who can concentrate many months of costly human effort to find a single bug. Closing this gap erodes the attacker’s long-term advantage by making all discoveries cheap.

**Encouragingly, we also haven’t seen any bugs that couldn’t have been found by an elite human researcher.** Some commentators predict that future AI models will unearth entirely new forms of vulnerabilities that defy our current comprehension, but we don’t think so. Software like Firefox is designed in a modular way for humans to be able to reason about its correctness. It is complex, but not arbitrarily complex

1.

The defects are finite, and we are entering a world where we can finally find them all.

1  There’s a risk that codebases begin to surpass human comprehension as a result of more AI in the development process, scaling bug complexity along with (or perhaps faster than) discovery capability. Human-comprehensibility is an essential property to maintain, especially in critical software like browsers and operating systems.

This post is also available in:
[Deutsch (German)](https://blog.mozilla.org/de/privacy-security-de/ki-sicherheit-zero-days-schwachstellen/) [Français (French)](https://blog.mozilla.org/fr/privacy-security-fr/securite-ia-vulnerabilites-zero-day/)
