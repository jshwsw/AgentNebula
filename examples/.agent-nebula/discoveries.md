# Discoveries Archive

Auto-archived session findings from progress.md.
Each entry below is the "Last Session" snapshot captured by the orchestrator before the agent overwrites progress.md.

---

## Last Session (#9)
- Task: T006 — TSUseCameraData documentation
- Result: completed
- Key findings: 96.8% use setType=0 (CamCurveMovie), 100% use doScriptTargetType=1 (CamTargetMain). TSUseCameraData is Target Script version of GSControlCameraData. cancelSet open/close pairs are standard pattern. Analysis 1538 lines, Reference 335 lines.

---

## Last Session (#17)
- Task: T015 — GSControlAIData documentation
- Result: completed
- Key findings: AI control script with 3 modes: enable/disable/reset. 45 occurrences across 11 roles. Always paired with combat state transitions. Disable mode most common (67%) for cutscene/finishing move sequences. Analysis 1423 lines, Reference 289 lines.

---

## Last Session (#21)
- Task: T018 — GSCreateShadowBodyData documentation
- Result: completed
- Key findings: Shadow body creation script with 6 parameters. Uses KF8World::CreateKFActor for spawning shadow entities. 23 occurrences across 5 roles, primarily in 60014 (weapon shadow clones). Top companion: GSAccessoryOperationData for weapon visibility sync. Analysis 1875 lines, Reference 312 lines.
