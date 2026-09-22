# Security

## Supported versions

Security fixes are released for the latest `1.x` version.

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability. Use the repository's
[private vulnerability reporting form](https://github.com/AgentHangar/evals/security/advisories/new)
and include reproduction steps and impact. Reports are visible only to the
repository maintainers until they coordinate a fix and disclosure with you.

## Protecting benchmark data

Task packs contain held-out tests and known-good solutions. They may also
contain proprietary source patches and private repository locations. Store real
task packs, product configuration, transcripts, raw outputs, and reports in a
separate private workspace. Never commit them to this repository, even briefly.

Agent harnesses execute third-party CLIs against working copies of code. The
Claude Code, Codex, and Cursor harnesses intentionally use unrestricted,
unattended permission modes so trials can finish without human approval. The
agent therefore has the access of the user running `bench`. Use this carefully:
run only task packs, prompts, repositories, test commands, Docker images, and
agent CLI configurations you trust, and be mindful of credentials and sensitive
files available on your computer. Docker grading uses networking disabled, but
it isolates only the grading command—not the agent that produces the candidate
change.

Transcript surveying reads local session files. Inspect the selected directory
before running it and do not publish the resulting source material.

## Answer isolation

The engine exports a fresh starting tree for the agent, with one synthetic Git
commit and no remotes, and grades its captured diff in another checkout. This
reduces accidental answer leakage from later commits and workspace residue. It
does not restrict host filesystem access: use an agent sandbox with only approved
inputs and no access to private task packs, original repositories or grader data.
Protected paths stop ordinary test edits; they do not make local execution safe
against hostile application code or test-runner manipulation.
