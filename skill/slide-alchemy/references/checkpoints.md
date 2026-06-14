# Review Stops

Use at most two review stops by default. Both stops happen before element extraction so the workflow does not spend tokens and time rebuilding assets on the wrong base.

## Stop 1: Base Grouping

Stop after inspecting source pages and proposing base groups.

Deliver:

- recommended page groups,
- a short reason for each group,
- whether each group is cover, content, ending, or custom.

Wait for the user to approve or edit the grouping before generating bases, unless the user explicitly asked for an unattended full run.

## Stop 2: Clean Bases

Stop after generating clean base images.

Deliver:

- base preview images,
- the base grouping used,
- a short note about whether the center is clean or containers were intentionally preserved.

Wait for the user to approve or request regeneration.

Do not continue to icon or text extraction before approval unless the user explicitly says to run the whole process automatically.

## Asset QA Is Not A Stop

After assets are generated:

- `element_analysis.json` is written,
- PNG assets are sliced,
- contact sheets are generated,
- edge-touch checks are clean or explained.

Use those artifacts for QA, but do not wait for user approval before composing the final PPTX.

Regenerate assets only when QA finds a hard problem such as clipped icons, source-cropped assets, polluted crops, missing components, or simple geometry wrongly rasterized into PNG.

## Final Delivery

Compose the PPTX and export preview images.

Deliver:

- final PPTX,
- preview images or comparison images when useful,
- any residual warnings.

## When To Skip

Skip the two base-stage review stops only when the user explicitly asks for a full automatic run, batch processing, or no intermediate confirmation.
