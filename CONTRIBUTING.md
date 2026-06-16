# Contributing to Slide Alchemy

First of all, thank you for your interest in contributing! This document will help you understand how to contribute effectively.

## How to Contribute

There are many ways to contribute:

- **Bug reports**: Open an issue describing the problem, your environment, and steps to reproduce.
- **Bug fixes**: Submit a PR that fixes a specific, documented issue.
- **Documentation improvements**: Fix errors, add clarity, or translate existing docs.
- **New reference documents**: Add missing reference docs that help agents execute the workflow more reliably.
- **Script improvements**: Fix bugs or add features to the bundled Python scripts.

## Before You Start

- Python 3.10+ is the only required runtime dependency.
- Install script dependencies from `skill/slide-alchemy/requirements.txt` if you plan to test scripts.

## PR Triage

This is a small project. To respect everyone's time, please follow this guidance:

| Contribution type | What to do |
|---|---|
| Typos, small doc fixes | Open an issue. PRs are welcome but not required for trivial fixes. |
| Bug fixes | PRs are very welcome. Reference the issue number. |
| New features or workflow changes | **Open an issue first** to discuss direction before writing code. |
| Refactoring or structural changes | **Open an issue first.** Large refactors may not align with the project's scope. |

### What we do NOT accept

- Switching from `pip + requirements.txt` to `uv`, `poetry`, or other package managers.
- Adding CI pipelines, test frameworks, or pre-commit hooks. This is intentional for a lightweight skill project.
- Repackaging the skill as a CLI tool, SaaS, or desktop application.
- Mass renames or structural reorganization without prior discussion.

## Contribution Workflow

1. Fork the repository.
2. Create a feature branch from `main`.
3. Make your changes. Keep PRs focused — one concern per PR.
4. If you changed a script, verify it runs without errors.
5. If you changed `SKILL.md` or reference docs, verify the workflow still makes logical sense end-to-end.
6. Submit your PR with a clear description of what changed and why.

## Review Process

- Expect an initial response within a few days.
- If a PR requires more than 2 rounds of changes to converge, it may be closed with a note. This is not gatekeeping — it is protecting your time. You are welcome to resubmit with a clearer direction.
- Keep discussions constructive and focused on the code.

## SVG Compatibility

If your contribution involves SVG generation for the PPTX output, ensure your SVG does not use:

- `<mask>` or `opacity` attributes (PowerPoint does not reliably render them)
- `<style>` blocks with CSS classes (PowerPoint ignores embedded stylesheets)
- `foreignObject` (not supported in PowerPoint SVG import)
- `<use>` with external references (PowerPoint cannot resolve them)
- Non-standard fonts or system-dependent font names

Prefer inline `style` attributes with absolute values (colors as hex, dimensions in px or emu).

## Bug Reports

When filing a bug report, please include:

1. The step in the workflow where the issue occurred.
2. The input (source slide type, page count, etc.).
3. The expected vs. actual behavior.
4. Any error messages or unexpected output artifacts.
5. The AI model and environment you used (if relevant).

## Code of Conduct

Be respectful. Be constructive. We are all here to make slide reconstruction better.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
