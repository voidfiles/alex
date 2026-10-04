## Galactic Compass 2: now with new augmented reality mode

##### 11.44, Friday 21 Aug 2026 [Link to this post](https://interconnected.org/home/2026/08/21/galactic)

I updated my *Galactic Compass* app for iPhone with **augmented reality** mode.

Background:

*Galactic Compass* is a floating green arrow that always points the way to the middle of the Milky Way, 26,000 light years away.

[Here’s the announcement blog post](https://interconnected.org/home/2024/02/15/galactic-compass) from 2024.

It went kinda viral at the time. It was in the “top free apps” charts at the App Store briefly. In the *Travel* category. ([I keep a list of press mentions over on Acts Not Facts](https://www.actsnotfacts.com/made/galactic-compass).)

Why so popular? Probably because it was early “vibe coding” – I copy-and-pasted between ChatGPT and Xcode to code it, and that was new at the time.

But ALSO because knowing where the galactic centre is surprisingly grounding? I wake up every few months to an email in my inbox from someone who is having a tough time in life, or is losing a loved one, or similar, and somehow they have discovered *Galactic Compass* and they tell me how they sit outside at night with a cigarette and gaze at the arrow and it gives them a place of comfort and infinity.

I know what they mean. The Earth spins; it turns around the Sun; and so, at first, the supermassive black hole of the galaxy appears to slowly whirl around us, above and under the horizon, round and round. But then your perspective flips, and we are the ones moving, and the centre of the galaxy becomes a fixed point, our rock.

Anyway *Galactic Compass 2* has two new features:

- **Augmented reality mode.**You can place the arrow in the world around you and walk around it.
- **Apple Watch app.**See the compass arrow on your wrist (tap to use*alignment mode*which gives you a haptic bump when the arrow is pointing straight ahead).

Plus a new Liquid Glass appearance ready for iOS 27.

[Download Galactic Compass from the App Store.](https://apps.apple.com/gb/app/galactic-compass/id6451314440)

Some “making of” notes:

Apple’s in-camera augmented reality is really, really good. Like, the arrow remains rock solid as you walk around. I hope they keep improving it.

I added a specific interaction that I’m intrigued by: you can hold down on the compass around to “drag” it around. It remains about 75cm away in phone reference frame, then drops into world frame when you release. I like how fluid it feels. My phone starts to feel like a glove that can reach into the virtual.

With the Apple Watch app… RealityKit, Apple’s graphics SDK, isn’t supported on watchOS. So how does the arrow rotate any which way? The joy of AI and [agents that grind problems into dust](https://interconnected.org/home/2026/03/28/architecture): Claude Fable built its own 3D graphics library. Astounding.

It isn’t all fire-and-forget vibing with AI agents:

That first version of *Galactic Compass* didn’t work when you lifted your phone higher than about 30 degrees. ChatGPT couldn’t get the maths right.

And there is a lot of maths: device rotation, world frame rotation, astro… the appropriate way to combine these 3D rotations (and avoid gimbal lock) is a method called “quaternions” which - despite my physics background - I have never grasped.

After I released version 1.0, I figured I would have to do the rotations myself. So I sat down with ChatGPT and I didn’t get it to write the code, but I got it to educate me. With a patient, interactive tutor, I was able to finally do what I hadn’t by reading books and asking mathematician friends – I learnt how to use quaternions just enough to make the app work.

So learning doesn’t stop just because I outsource a bunch of thinking to AI. It pushes me to learn more. I like that as an outcome.
