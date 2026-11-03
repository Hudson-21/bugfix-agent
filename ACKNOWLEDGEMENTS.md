# Dependencies and related work

This project was developed with AI assistance. Its tests, examples, and observed live-run results are included so behavior can be inspected and reproduced. AI-generated patches still require human review.

## Runtime dependency

- [pytest](https://github.com/pytest-dev/pytest) — MIT license; executes regression tests and produces JUnit results. Installed as a dependency, not vendored.
- Other runtime modules come from the Python standard library.

## Build and CI tools

- [setuptools](https://github.com/pypa/setuptools) — MIT license; Python package build backend.
- GitHub Actions uses `actions/checkout`, `actions/setup-python`, and `actions/upload-artifact`, each under the MIT license. They are referenced as actions, not copied into this repository.

## Related projects consulted

- [SWE-agent](https://github.com/SWE-agent/SWE-agent) — autonomous tool use for software repair; MIT license. Its README recommends mini-swe-agent for new work.
- [SWE-bench](https://github.com/SWE-bench/SWE-bench) — reproducible evaluation of patches against software issues; MIT license.

These projects informed the research discussion. This repository does not vendor their code, run their benchmark, or claim comparable performance. The three bundled examples are small, purpose-written fixtures.
