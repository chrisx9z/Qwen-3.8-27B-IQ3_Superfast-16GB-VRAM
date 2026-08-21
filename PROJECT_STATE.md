# M Auto Pilot Project State

## Architecture boundary

M Auto Pilot is the controller. AI Video Localizer is an external target application. The controller owns its own source, state, runtime, models, and build output.

## Checkpoint 2026-08-22

- Restored D:\AI-Video-Localizer tracked files changed by the previous embedded Auto Pilot implementation.
- Created standalone root D:\M-Auto-Pilot.
- Copied the current Auto Pilot controller/UI code into the standalone root for refactoring.
- Switched local root/state resolution to M_AUTO_PILOT_ROOT.
- Added an explicit target descriptor through M_AUTO_PILOT_TARGET_ROOT and M_AUTO_PILOT_TARGET_EXE.
- Standalone dependency check and direct Bilibili search smoke test passed from D:\M-Auto-Pilot.
- Generic Internet research smoke test passed: searched and opened Python 3.14 documentation, plus returned a Douyin search page when public video results were unavailable.
- UI progress narration now writes each status, search, source-open, and tool-result step into the result panel.
- Business Plan handoff is saved in `docs/BUSINESS_PLAN_HANDOFF.md`.
- Browser open/snapshot/close, coding compile/checkpoint, and controlled application-launch smoke tests passed.
- M Auto Pilot now has its own Git repository with a baseline commit; AI Video Localizer remains a separate clean worktree.
- Development is paused for low-VRAM stability. Desktop cleanup kept only the latest build as `M Auto Pilot.exe`; older Desktop builds are outside Desktop in `archive/desktop-old`.
- Standalone executable built at D:\M-Auto-Pilot\dist\M Auto Pilot.exe; the previous Desktop executable is still running, so the verified copy is D:\OneDrive\Desktop\M Auto Pilot Standalone.exe.
- Do not build the final executable from D:\AI-Video-Localizer.

## Next implementation boundary

- Keep generic web research independent from platform-specific optimizations.
- Move target-specific actions behind adapters/ai_video_localizer.py.
- Add UI Automation/API actions for launching, reading status, and controlling Localizer.
- Keep browser, shell, coding, and Windows-control tools in M Auto Pilot.
- Extend model-backed multi-step planning and source synthesis after the basic control path is stable.
- Build the final executable from this root only.
