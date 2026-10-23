# Release status

## Public release · 2026-10-23

- Self-contained Skill, local video intake, host Agent analysis, schema 3.0 coaching report and optional H5 are implemented.
- macOS / Python 3.12 / Codex: 12 focused behavioral checks passed; independent actual-video analysis, pose review and browser interaction checks completed locally.
- Release ZIP excludes user videos, reports, model weights, caches and environments. Package integrity and extracted runtime inspection passed.
- Claude Code, WorkBuddy and other operating systems have not completed end-to-end validation. Coaching accuracy, NTRP calibration and training efficacy are not benchmarked.
- Public source: [maxmax-hub/tennisprism](https://github.com/maxmax-hub/tennisprism). Anonymous download of source commit `34d22a8` matched all 42 tracked files byte for byte; no user media is included.
- [GitHub Actions validation](https://github.com/maxmax-hub/tennisprism/actions/runs/39914622599) passed on Ubuntu / Python 3.12: 12 behavioral tests, both browser-script syntax checks and the 29-file standalone package. One upstream Starlette/httpx deprecation warning remains.
- [Actual public installation](https://github.com/maxmax-hub/tennisprism/actions/runs/39914662697) passed with the official skills CLI 1.7.4 in an isolated GitHub-hosted runner: 29 installed files matched, Python dependencies installed and `coach.py doctor` reported ready. This verifies installation and local dependencies, not an additional host Agent's coaching behavior.
- [skills.sh page](https://skills.sh/maxmax-hub/tennisprism/tennisprism) is accessible with the correct install command and Skill content. Its install counters may update separately.
- At publication, skills.sh showed Agent Trust Hub PASS and [Snyk WARN W011](https://skills.sh/maxmax-hub/tennisprism/tennisprism/security/snyk), flagging user-supplied focus/player descriptions as an indirect prompt-injection exposure. This is a third-party automated label; no claim of a clean security audit is made. The Skill remains subject to the host's instruction hierarchy and tool permissions.

Stable workflow and interfaces: README.md and docs/development.md. Private validation media and logs are intentionally not published.
