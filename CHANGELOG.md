# Changelog

## [0.4.0](https://github.com/iloveitaly/pytest-playwright-artifacts/compare/v0.3.1...v0.4.0) (2026-05-21)


### Features

* **config:** add domain-based console error filtering ([d554c56](https://github.com/iloveitaly/pytest-playwright-artifacts/commit/d554c56fd0bf24bab5e860181547b4f8d02fd2e9))


### Bug Fixes

* cast to Any for custom rerun outcome ([db66365](https://github.com/iloveitaly/pytest-playwright-artifacts/commit/db66365ecd1917ee348f147a2a58958fbbee7352))
* handle non-serializable console message arguments ([e675941](https://github.com/iloveitaly/pytest-playwright-artifacts/commit/e6759416c7804eca9d2f0813b26ff8033ed30c21))


### Documentation

* add domain-based filtering to console ignore rules ([a7693e7](https://github.com/iloveitaly/pytest-playwright-artifacts/commit/a7693e73675320849c1865034ba6f1dfce44df5e))

## [0.3.1](https://github.com/iloveitaly/pytest-playwright-artifacts/compare/v0.3.0...v0.3.1) (2026-03-23)


### Bug Fixes

* triggering a build for the fixed upstream utils refactor ([565d032](https://github.com/iloveitaly/pytest-playwright-artifacts/commit/565d0323a0bd4cee87e6f0795e8ffe9af74cf7d2))

## [0.3.0](https://github.com/iloveitaly/pytest-playwright-artifacts/compare/v0.2.0...v0.3.0) (2026-03-17)


### Features

* change console log output format to JSONL ([#23](https://github.com/iloveitaly/pytest-playwright-artifacts/issues/23)) ([48ede9b](https://github.com/iloveitaly/pytest-playwright-artifacts/commit/48ede9bf711f676059721bd38325832544039d7a))
* **plugin:** preserve console logs for single-test runs and display in terminal summary ([22cb0a1](https://github.com/iloveitaly/pytest-playwright-artifacts/commit/22cb0a1990be1c69b7f88e47c8333b5379ff70d6))


### Documentation

* add example log line for console ignore patterns ([5cc5607](https://github.com/iloveitaly/pytest-playwright-artifacts/commit/5cc56076e382df2e427bf2630781cd21f1d00fe7))
* clarify console log capture behavior in README ([2df3b8c](https://github.com/iloveitaly/pytest-playwright-artifacts/commit/2df3b8c0523705fb5e00ee6916138929766491c2))
* clarify console log filtering by URL/location ([db5049e](https://github.com/iloveitaly/pytest-playwright-artifacts/commit/db5049e783980dc519fdf6e4853e587d1aa5b276))
* clarify console log ignore pattern syntax and scoping ([24c74e3](https://github.com/iloveitaly/pytest-playwright-artifacts/commit/24c74e3c1f33a6e2a77e7749be384202bac9ff84))

## [0.2.0](https://github.com/iloveitaly/pytest-playwright-artifacts/compare/v0.1.0...v0.2.0) (2026-02-19)


### Features

* Add ignore and ignore_defaults args to assert_no_console_errors ([70c3f5d](https://github.com/iloveitaly/pytest-playwright-artifacts/commit/70c3f5dadbff7f015e7b203e13f38310d236d5f0))
* Add ignore and skip_defaults args to assert_no_console_errors ([76bdc65](https://github.com/iloveitaly/pytest-playwright-artifacts/commit/76bdc657c3403b4831900202bbbabdc32d1dfb1a))
* **config:** add pytest option registration and retrieval utilities ([570669e](https://github.com/iloveitaly/pytest-playwright-artifacts/commit/570669e36e82abf5e1dd043853cdf8b71c8c9f8f))


### Bug Fixes

* set artifact dir option during pytest configuration ([1ad9e71](https://github.com/iloveitaly/pytest-playwright-artifacts/commit/1ad9e711602772542a03d2bdd9869f9cf3b57b61))


### Documentation

* add Gemini link to config.py for reference ([7f2e7ff](https://github.com/iloveitaly/pytest-playwright-artifacts/commit/7f2e7ff0b919002e735d2d8508d546531f0c84d1))
* add MIT license file ([055a44b](https://github.com/iloveitaly/pytest-playwright-artifacts/commit/055a44ba66ef80e50fc6ab4e60f9bc3d01ce2022))
* add related projects section to README ([216563f](https://github.com/iloveitaly/pytest-playwright-artifacts/commit/216563fe8cff82cdc7a151df0e68daf60e7c9c05))
* clarify artifact output directory customization options ([864a221](https://github.com/iloveitaly/pytest-playwright-artifacts/commit/864a22128a1415214577eec3b86f6af39c2a4a6e))
* clarify option resolution logic and caveats in config module ([c1aa060](https://github.com/iloveitaly/pytest-playwright-artifacts/commit/c1aa060c9f623a69c706c0e6081fa0503e02030a))
* clarify readme prompts and metadata update rules ([9e1612b](https://github.com/iloveitaly/pytest-playwright-artifacts/commit/9e1612b7ca283efc481482066e6f1a19cd052364))
* clarify rules on app/generated files and env safety ([69ac8c9](https://github.com/iloveitaly/pytest-playwright-artifacts/commit/69ac8c962f95d7a9d304b7d1de69cf43de12aa1e))
* document and implement retry on Playwright TimeoutError ([bd13214](https://github.com/iloveitaly/pytest-playwright-artifacts/commit/bd132140b470aa1b2a8d37ed7fe8de5f0a44fe66))
* Fix formatting of MIT License link in README ([fa4cf67](https://github.com/iloveitaly/pytest-playwright-artifacts/commit/fa4cf67e3f17258687c3d6ff3f674beea8b8460f))
* reword description, keywords; fix README usage section ([ef41fbd](https://github.com/iloveitaly/pytest-playwright-artifacts/commit/ef41fbd5aa0df881ff37ef4d59c822a9e3d7c720))
* update artifact output option and refactor path helpers ([9d8b9a1](https://github.com/iloveitaly/pytest-playwright-artifacts/commit/9d8b9a1dc7a5c541720c88a815d2e62c2017054c))
* update CLAUDE.md with new agent instruction reference ([48d69eb](https://github.com/iloveitaly/pytest-playwright-artifacts/commit/48d69eb870ae44db861f7ba9a25ca5cebe321995))

## 0.1.0 (2026-01-29)


### Features

* **pytest:** add plugin for playwright failure artifacts ([a882c13](https://github.com/iloveitaly/pytest-playwright-artifacts/commit/a882c13a53056d2191ae253d71704fe5f72c3ad8))
* restructure as pytest plugin, add readme and tests ([dcdf7e5](https://github.com/iloveitaly/pytest-playwright-artifacts/commit/dcdf7e527c69bf5d3bbe7e26360a3b29a40e22ab))


### Documentation

* document failure artifacts and update logging setup ([ffaadf2](https://github.com/iloveitaly/pytest-playwright-artifacts/commit/ffaadf2188534800737cd4ddb9c1dac3f36fb42d))
