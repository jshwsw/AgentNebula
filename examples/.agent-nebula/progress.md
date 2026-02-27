# Progress: TitusEditor-ScriptDocs

## Overall
- Completed: 18 / 152 tasks (12%)
- Sessions so far: 21
- Current phase: Batch generation of p3 script documentation (Analysis + Reference for each undocumented KF8 script type)

## Last Session (#21)
- Task: T018 — GSCreateShadowBodyData documentation
- Result: completed
- Key findings: Shadow body creation script with 6 parameters. Uses KF8World::CreateKFActor for spawning shadow entities. 23 occurrences across 5 roles, primarily in 60014 (weapon shadow clones). Top companion: GSAccessoryOperationData for weapon visibility sync. Analysis 1875 lines, Reference 312 lines.

## Key Discoveries
- Scripts marked FTYPE=abandoned in KFD are deprecated and should not be used in new data
- ExistSkillObjRef extraction tool handles 0-usage scripts gracefully (warns but doesn't fail)
- Scripts with 0 usage still need documentation for completeness, but documents are shorter (theoretical examples only)
- Some KFD class definitions have inconsistent P= casing (uppercase P=1, lowercase p=2) but the parser is case-insensitive
- GSSetAnimationAimModeData has deprecated FaceTarget param replaced by separate aim mode controls
- TSUseCameraData is the Target Script version of GSControlCameraData; shares GSCamCurveMovieParam types
- GSAccessoryOperationData has 16 parameters in 3 functional modules (animation/socket/visibility) + independent transition control
- Role 60014 is the heaviest user of weapon-related scripts (accessory, shadow body)

## Known Issues & TODOs
- None currently blocking

## Next Up
- T019: Generate Analysis and Reference documentation for TSThrowTargetData
