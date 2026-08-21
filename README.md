# M Auto Pilot

M Auto Pilot is an independent computer-control application.

AI Video Localizer is a target application controlled through adapters, UI Automation, browser tools, APIs, or approved workspace commands. M Auto Pilot must not import AI Video Localizer modules or modify its source files.

## Paths

- M Auto Pilot root: D:\M-Auto-Pilot
- AI Video Localizer target: D:\AI-Video-Localizer
- Target executable: D:\OneDrive\Desktop\AI Video Localizer.exe

## Runtime variables

- M_AUTO_PILOT_ROOT controls M Auto Pilot state, chats, logs, models, and runtime files.
- M_AUTO_PILOT_TARGET_ROOT identifies the application workspace to control.
- M_AUTO_PILOT_TARGET_EXE identifies the target executable.

## Current separation checkpoint

- The AI Video Localizer Git worktree was restored to its pre-M-Auto-Pilot state.
- M Auto Pilot source was copied here for independent refactoring.
- The AI Video Localizer adapter boundary is defined in adapters/ai_video_localizer.py.

## Core capability roadmap

1. Web research: search the Internet, open relevant sources, extract content, and return URLs and source excerpts.
2. Computer control: inspect Windows/browser state and perform approved UI actions.
3. Coding agent: inspect, edit, run checks, create checkpoints, and verify workspace changes.
4. Target adapters: control AI Video Localizer and other applications without importing or changing their source.
5. Runtime reliability: streaming progress, task history, resumable checkpoints, Q4/Q6 profiles, and clear tool errors.

The web research pipeline is now implemented with a generic `web_search` route and a Bing fallback when the primary search endpoint is unavailable. Platform-specific search tools remain optional optimizations, not the architecture boundary.
