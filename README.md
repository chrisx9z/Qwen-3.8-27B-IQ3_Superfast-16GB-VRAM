# M Auto Pilot

M Auto Pilot is a standalone local-first agent for web research, Windows/browser control, coding tasks, and application automation.

## Software boundary

M Auto Pilot and AI Video Localizer are two separate applications:

- M Auto Pilot owns the controller, UI, tools, chats, runtime state, models, and build output.
- AI Video Localizer is an external application that M Auto Pilot may control.
- M Auto Pilot does not import AI Video Localizer code and does not modify its source files.

## Locations

- M Auto Pilot: `D:\M-Auto-Pilot`
- AI Video Localizer workspace: `D:\AI-Video-Localizer`
- AI Video Localizer executable: `D:\OneDrive\Desktop\AI Video Localizer.exe`
- M Auto Pilot executable: `D:\OneDrive\Desktop\M Auto Pilot.exe`

## Integration contract

The only target-specific configuration is supplied through the adapter:

- `M_AUTO_PILOT_ROOT`: M Auto Pilot state and runtime root.
- `M_AUTO_PILOT_TARGET_ROOT`: external application workspace.
- `M_AUTO_PILOT_TARGET_EXE`: external application executable.

The adapter exposes status and launch operations. Further control uses generic Windows UI Automation, browser automation, APIs, or approved commands.

## M Auto Pilot capabilities

1. Generic Internet research with search fallback, source opening, extraction, URLs, and excerpts.
2. Browser automation through open, snapshot, click, type, extract, screenshot, and close tools.
3. Windows UI Automation through window listing, control inspection, click, type, and keyboard tools.
4. Coding workflow with workspace reads, controlled edits, checkpoints, compile/test checks, and Git status/diff.
5. Qwen3.8 27B profiles: Q4 default and Q6 for complex requests.
6. Progress narration, chat history, resumable state, and clear tool errors.

## Current status

Development is temporarily paused because available VRAM is not sufficient to run M Auto Pilot and AI Video Localizer reliably at the same time.

- Source: `D:\M-Auto-Pilot`
- Build: `D:\M-Auto-Pilot\dist\M Auto Pilot.exe`
- Desktop build: `D:\OneDrive\Desktop\M Auto Pilot.exe`
- Project state: `PROJECT_STATE.md`
