# M Auto Pilot Project State

## Separation rule

M Auto Pilot and AI Video Localizer are separate applications.

- M Auto Pilot owns this repository, its UI, tools, chats, runtime files, models, and builds.
- AI Video Localizer is an external target application.
- M Auto Pilot may inspect or control the target through the adapter and generic automation tools.
- M Auto Pilot must not import target modules or modify the target source tree.

## M Auto Pilot locations

- Source and state: `D:\M-Auto-Pilot`
- Build output: `D:\M-Auto-Pilot\dist\M Auto Pilot.exe`
- Desktop executable: `D:\OneDrive\Desktop\M Auto Pilot.exe`
- External target workspace: `D:\AI-Video-Localizer`
- External target executable: `D:\OneDrive\Desktop\AI Video Localizer.exe`

## Implemented

- Generic web research with search fallback and source extraction.
- Browser automation and Windows UI Automation.
- Controlled `.exe` launch within approved directories.
- AI Video Localizer adapter for status and launch.
- Coding tools for read, controlled edit, checkpoint, compile/test, and Git verification.
- Qwen Q4/Q6 profile selection and progress narration.
- Independent Git repository for M Auto Pilot.
- Latest Desktop build retained; older Desktop builds moved out of Desktop.

## Verification

- M Auto Pilot source compiles successfully.
- Browser open/snapshot/close smoke test passed.
- Generic web research smoke test passed.
- AI Video Localizer adapter status test passed.
- AI Video Localizer Git worktree is clean.

## Pause state

Development is temporarily paused due to low VRAM and crash risk when both applications run simultaneously. No model or source changes should be made until the runtime/resource plan is resumed.

## Resume priorities

1. Add a resource guard to prevent simultaneous high-VRAM workloads.
2. Continue multi-step Qwen planning and source synthesis.
3. Extend adapter/UI control only without changing AI Video Localizer source.
