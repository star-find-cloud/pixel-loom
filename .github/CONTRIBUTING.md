# Contributing to Pixel Loom

The complete source is in `project/`. Run installation, tests and build commands from that directory.

Read [the contribution guide](../project/CONTRIBUTING.md), [developer instructions](../project/AGENTS.md) and [release preparation](../project/docs/RELEASE.md).

Please describe the problem, expected behavior, operating system and application version. Keep private artwork, session tokens, client settings and generated files out of commits and public reports.

Before proposing a code change, run the relevant regression tests and `python tools/build_release.py --check`. GUI changes also need the documented desktop smoke checks. A successful numeric check is not an artistic quality assessment.
