# Dependabot version updates introduce default package cooldown - GitHub Changelog

# Dependabot version updates introduce default package cooldown

Dependabot now waits until a new release has been available on its registry for at least three days before opening a version update pull request. This cooldown is now the default and requires no configuration.

New releases are a common entry point for supply chain attacks where a compromised or broken version can reach your dependency updates before maintainers and the community have caught it. A short delay gives that signal time to surface, so you are less likely to merge a bad release the moment it ships.

A few things to know:

- The default applies only to version updates. Security updates still open immediately, so critical fixes are never delayed.
- You stay in control. Use the

  ```
  cooldown
  ```

  option in your

  ```
  .github/dependabot.yml
  ```

  to set a different window or opt out entirely.

This default applies to Dependabot version updates across all supported ecosystems on github.com and will take effect in GitHub Enterprise Server (GHES) 3.23.

Learn more in [our docs about Dependabot cooldowns](https://docs.github.com/code-security/dependabot/working-with-dependabot/dependabot-options-reference#cooldown-).
