# Release status

## 1.0.2 · Conclusions and H5 together · 2026-10-24

- Direct chat attachments and readable video paths now default to one delivery: actual evidence review, validated report, H5 generation, working-link check, then concise conclusions/practice and the report link together. No second confirmation or diagnostic pass. Explicit text-only requests skip H5.
- Missing or unreliable optional pose data does not block the video/coaching report. Only real, reviewed pose may appear. Direct input is no longer instructed to use web-listener heartbeat commands. Web intake retains the 1.0.1 active-host flow and local H5 button.
- Scope is Skill orchestration, references, UI metadata, installation/use documentation and the runtime version label; media processing, report validation and H5 generation code are unchanged. Official Skill validation, Python parsing, local reference checks, UI metadata validation and canonical/public resource comparison passed. Existing 1.0.1 runtime and real-media/browser evidence remains applicable; this patch is not a new independent model/host video-analysis trial.
- Compatibility limits remain: QwenWork/千问办公 and other untested hosts are not claimed end-to-end verified. No user media, reports or model weights are distributed.

## 1.0.1 · Web continuation repair · 2026-10-24

- Root cause: 1.0.0 allowed the host Agent to finish after opening the upload page. The server prepared media but never invoked a model, leaving the user to send another chat message. This was a workflow gap, not an upload failure.
- The Skill now keeps the current host turn waiting for web submission. Real wait/heartbeat calls expose an expiring connection; the webpage and API reject new uploads/runs without a listener. Browser polling cannot maintain a fake online state. Closing or stopping the host task is still a real interruption; this is not a standalone model backend or a cross-host chat wake-up integration.
- Supplemental sampling inherits the current target/focus and links the replacement run; the page follows it automatically. Stale superseded reports are rejected. The H5 button now builds locally from the validated report without another model/chat turn; errors and interrupted builds can be retried. Unreviewed skeletons remain absent.
- 18 focused behavioral tests passed after the final code changes, plus both JavaScript syntax checks, Python parsing and official Skill validation. Tests cover disconnected submission, dispatch/expiry, browser polling not extending a lease, duplicate consumers, supplementation, H5 generation/errors/restart/retry and existing evidence/origin safeguards. The original application's unrelated full suite was not rerun.
- Real macOS / Python 3.12 / Codex browser check: selected/uploaded the authorized short MOV, clicked Start, received the task via the real wait command, viewed actual overview/sequence images, supplemented sampling, submitted an evidence-bound report, and saw it automatically appear on the original page. Clicked H5, opened the generated report, sought evidence, advanced a frame (23.835333 s; media readyState 4; no playback error), and restored the result after reload. No additional user chat instruction or model API key was needed. Original/copy hashes match. No pose inference was run for this fix.
- QwenWork/千问办公, Claude Code and WorkBuddy have **not** completed end-to-end validation. The design requires the host to keep the active task running; format compatibility does not prove lifecycle compatibility. No claim of background wake-up support or coaching accuracy.
- Core fix commit `650ce93` passed [Ubuntu CI](https://github.com/maxmax-hub/tennisprism/actions/runs/39986246009) and [real public installation](https://github.com/maxmax-hub/tennisprism/actions/runs/39986307284) with skills CLI 1.7.4. The final package includes a browser-checked report-link contrast adjustment. Private videos, reports, logs and screenshots remain excluded.

## 1.0.0 public release · 2026-10-23

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
