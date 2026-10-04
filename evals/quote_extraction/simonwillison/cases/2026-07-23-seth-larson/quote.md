The Python Package Index (PyPI) now rejects new files being uploaded to releases that are older than 14 days. This restriction was [put in place](https://github.com/pypi/warehouse/pull/19727) to prevent old and long-stable releases from being poisoned in case publishing tokens or workflows of PyPI projects were compromised. As far as we are aware this has not yet been abused, but there is no technical reason beyond that attackers weren't aware it was possible.

— Seth Larson

Source: https://blog.pypi.org/posts/2026-07-22-releases-now-reject-new-files-after-14-days/

Selected by Simon Willison: https://simonwillison.net/2026/Jul/23/seth-larson/
