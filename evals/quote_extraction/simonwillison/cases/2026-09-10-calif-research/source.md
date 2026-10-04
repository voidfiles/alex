[← Research](https://calif.io/research)

# WeWorm

The first zero-click worm to spread through WeChat calls across iOS and Android.

### Contents

At Calif, our mission is to keep the Internet together by occasionally taking it apart. We believe everyone deserves a safe and secure Internet, including the people who cannot protect themselves.

Today, we're releasing a demo of WeWorm, the first zero-click worm to spread through WeChat calls across iOS and Android. This is the first installment in a series exploring zero-click attack surfaces in mobile messaging apps.

WeChat is an "everything app" used by virtually everyone in China and by Chinese communities worldwide. Simply by calling a victim, WeWorm can hijack their account and call their friends, spreading from phone to phone. If exploited, actors can compromise over a billion phones (or accounts), upending livelihoods and breaking communities worldwide.

We built a demo worm with three phones:

The first Android phone, a Pixel 10a, is the attacker. We used it to call the second phone, an iPhone 17e, and exploited the bug to take over its WeChat while it was still ringing. We then used the compromised iPhone to call the third phone, another Pixel 10a, and took that one over the same way. Attacker calls victim, victim becomes attacker, victim calls the next victim.

You can also watch individual [Android](https://www.youtube.com/watch?v=k5mlLbyAknw) and [iOS](https://www.youtube.com/shorts/sVdRZ4x-hOk) RCE demos.

Exploitation takes only seconds, and gives us full control of the WeChat account. We can read and send messages, make calls, and act on the victim's behalf. Chained with other [Android](https://calif.io/research/oempocalypse) and iOS bugs we've reported and are helping fix, it can lead to full control of the device.

The victim does not need to answer the call, or interact with their phone at all. Even if they do answer, they hear nothing, and the exploit still succeeds. Declining the call stops that attempt, but the attacker can simply try again later, for example, while the victim is asleep.

This exploit requires the attacker to be on the victim's friend list. But that's not much of a barrier: an attacker can compromise one of your friends first and use their account to reach you.

WeChat, like many messaging apps, gives trusted contacts more privileges. But once one contact is compromised, that trust works against you.

Sophisticated attackers have many ways to do this. They could exploit another app, gain root access using techniques like those in [OEMpocalypse](https://calif.io/research/oempocalypse), take over the victim's WeChat app, and use it to attack you.

Working with AI, our team found the bug and wrote the first remote code execution (RCE) exploit in about two days. Building the worm took one more week.

A worm at this scale used to be the kind of thing that took a larger team months. AI can already do most of the work here. Our team provided the judgment about what to target and how to test it safely.

We are publishing our findings to raise public awareness. These capabilities have existed for a long time in the hands of well-funded, sophisticated actors. What's different now is that AI is putting these capabilities in the hands of less skilled actors, leaving ordinary users at unprecedented risk.

All it takes is one lab accident or a person who grabs a half-finished version, to unleash something like WeWorm into the world before anyone is ready. WannaCry got out that way, from tooling that escaped early and hit hospitals.

The easy reaction is to blame AI and try to curtail its further development. We think that is the wrong lesson. The vulnerabilities are already out there. What AI changed is that we can find and fix them fast. We believe there are more good guys than bad guys, and if they're paying attention, AI gives the good guys the upper hand.

We reported the WeChat bug to Tencent in July. As of today, they have mitigated our exploit for all users. We'd like to thank Tencent for a successful collaboration.

We hope this work is an example of what we can achieve together. It is a call for the United States, China, and other governments to work together and collaborate with private industry on developing and deploying AI to make the world safer for everyone.

## The bug

The bug is a memory corruption issue in WeChat's VoIP stack. We're withholding the technical details for now. We plan to present the full analysis at an upcoming conference.

This specific WeChat bug is one instance of the many unconventional attack surfaces that are present across many messaging apps. We're conducting more of this research across other apps and attack surfaces, while working with app developers on attack surface reduction. This may take an industry-wide effort, since some of it depends on the platform owners. Once that work is further along, we'll share our progress, including the technical details of this WeChat bug.

## Disclosure timeline

- Sometime in July, 2026: Our AI discovered the bug.
- July 23: Our engineering team became aware of the bug.
- July 24: We submitted the bug to Tencent.
- July 25-28: Our WeChat accounts were banned.
- July 29: Our WeChat accounts were unbanned.
- July 30: We completed the first Android RCE exploit.
- August 2: We completed the iOS RCE exploit.
- August 11: We completed the polished worm demo across Android and iOS.
- August 21: Tencent published Android 8.0.77 and iOS 8.0.76 that mitigated the bug.
- August 26: Tencent notified us that they're assessing the issue.
- August 28: We confirmed that our exploit was mitigated on the server side for all users.
- September 3: We shared our technical analysis and working exploits with Tencent.
- September 4: Tencent confirmed that the vulnerability could be exploited for remote command execution.
- September 8: We published this article alongside coverage from [The New York Times](https://archive.is/arHsF).
- September 11: [The New York Times](https://archive.is/spwCf)published a follow-up analysis of WeWorm and its implications for China.

About Calif

We push offensive security research to its limits, understand what is becoming possible with AI, and use those insights to help our customers defend themselves.

[Get in touch](https://calif.io/contact), and subscribe to our newsletter for more research
like this:

Check your inbox to confirm.

Related research
