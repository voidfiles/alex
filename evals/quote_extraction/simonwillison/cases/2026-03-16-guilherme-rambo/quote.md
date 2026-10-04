Tidbit: the software-based camera indicator light in the MacBook Neo runs in the secure exclave¹ part of the chip, so it is almost as secure as the hardware indicator light. What that means in practice is that even a kernel-level exploit would not be able to turn on the camera without the light appearing on screen. It runs in a privileged environment separate from the kernel and blits the light directly onto the screen hardware.

— Guilherme Rambo

Source: https://daringfireball.net/2026/03/apple_enclaves_neo_camera_indicator

Selected by Simon Willison: https://simonwillison.net/2026/Mar/16/guilherme-rambo/
