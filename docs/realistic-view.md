# Realistic replay prototype

Select **5 · Realistic** or press **5**. Other views remain on keys 1–4.

This local WebGL view uses Three.js 0.170.0 (vendored with its MIT license), procedural articulated player figures, listed heights when available, jersey numbers, court lighting and shadows. Player and ball paths come from replay tracking. Shooting poses follow recorded shot events; running and defensive joint poses are illustrative. The local tracking files do not contain body-joint coordinates. Figures are generic, not player likenesses. No model predictions are changed.

Pressure toggles subtle teal interception wings and amber block curves. Their dimensions express relative model threat, not physical reach. The selected pass determines the steal scenario.

For photorealistic quality, the next step requires detailed rigged human assets and captured basketball animation clips, or synchronized joint-pose data. Current figures are an interactive rendering prototype, not motion-captured reconstruction.

Verification: local browser rendering, Realistic/Tactical switching, JS syntax checks, and four existing playback tests passed.
