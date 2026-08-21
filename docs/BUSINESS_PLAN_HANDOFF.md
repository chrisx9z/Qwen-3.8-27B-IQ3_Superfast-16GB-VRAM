# M Auto Pilot — Business Plan Handoff

## Objective

Build a local-first computer-use and coding agent powered by Qwen3.8 27B, with Q4 as default and Q6 for complex requests.

## Architecture decision

- `D:\M-Auto-Pilot` is the controller application.
- `D:\AI-Video-Localizer` is an independent target application.
- M Auto Pilot must control the target through adapters, UI Automation, browser tools, APIs, or approved commands; it must not import or modify the target source tree.

## Core capabilities

1. Web research: search the Internet, use fallback providers, open sources, extract relevant text, and return URLs/source excerpts.
2. Computer control: inspect Windows/browser state and perform approved actions.
3. Coding agent: inspect, edit, test, checkpoint, and verify changes.
4. Application adapters: launch, inspect, and control AI Video Localizer without coupling its code.
5. Runtime: chat history, progress narration, resumable state, Q4/Q6 profiles, and clear errors.

## Current implementation

- Generic Internet search and source extraction are implemented and tested.
- Direct Bilibili, YouTube, and Douyin paths are optimizations only; they are not the web architecture.
- A standalone executable is built from `D:\M-Auto-Pilot`.
- AI Video Localizer worktree is clean after removing the previous embedded Auto Pilot changes.

## Next priorities

- Complete Windows/browser computer-use actions with confirmation policy.
- Move all target-specific operations behind adapters.
- Improve model-backed research synthesis and multi-step execution.
- Add end-to-end tests for search, coding, application control, restart, and failure recovery.
