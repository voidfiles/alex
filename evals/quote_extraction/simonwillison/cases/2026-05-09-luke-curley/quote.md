WebRTC is designed to **degrade and drop my prompt** during poor network conditions.

wtf my dude

WebRTC aggressively drops audio packets to keep latency low. If you’ve ever heard distorted audio on a conference call, that’s WebRTC baybee. The idea is that conference calls depend on rapid back-and-forth, so pausing to wait for audio is unacceptable.

…but as a user, I would much rather wait an extra 200ms for my slow/expensive prompt to be accurate. After all, I’m paying good money to boil the ocean, and a garbage prompt means a garbage response. It’s not like LLMs are particularly responsive anyway.

**But I’m not allowed to wait**. It’s *impossible* to even retransmit a WebRTC audio packet within a browser; we tried at Discord. The *implementation* is hard-coded for real-time latency **or else**.

— Luke Curley

Source: https://moq.dev/blog/webrtc-is-the-problem/

Selected by Simon Willison: https://simonwillison.net/2026/May/9/luke-curley/
