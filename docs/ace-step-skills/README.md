# ACE-Step Skills (reference knowledge)

This folder contains reference material from the official **ACE-Step Skills** repository, used as knowledge for AceForge development and for aligning with ACE-Step concepts (caption, lyrics, task types, API parameters).

**Source:** [ace-step/ace-step-skills](https://github.com/ace-step/ace-step-skills) — `skills/acestep/`  
**License:** See the upstream repository.

## Contents

| File | Description |
|------|-------------|
| [SKILL.md](./SKILL.md) | ACE-Step skill definition: API usage, generation modes, parameters, config. |
| [music-creation-guide.md](./music-creation-guide.md) | Music creation guide: caption, lyrics, structure tags, metadata, duration. |

## Note for AceForge

AceForge runs its own backend and API (Flask, `api/generate.py`, etc.), not the standalone ACE-Step API server on port 8001. The *concepts* (caption vs lyrics, task types, parameters, music-creation practices) still apply and are referenced when implementing or documenting AceForge features.
