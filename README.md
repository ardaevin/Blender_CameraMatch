# Camera Match

An fSpy-style camera matcher that runs **inside Blender's camera view**. Drag vanishing-point lines over the camera's background image and the active camera's focal length, rotation, position and (optionally) lens shift are solved live.

## Features

- **2 vanishing points**: solves focal length + rotation, principal point at image centre.
- **2 VP + VP3**: a third vanishing point also solves the principal point and writes it as lens shift.
- **1 vanishing point**: known focal length + a horizon-direction line.
- **Origin & scale**: place the world origin on the image; optionally set real-world scale from a known length along an axis.
- **Live feedback**: ground grid (XY / XZ / YZ) and world axes drawn through the solved camera, plus the horizon line.
- Respects the camera's sensor fit (Auto / Horizontal / Vertical) and render pixel aspect (anamorphic plates).
- Handles are stored on the camera data, so a match is saved with the .blend.

## Install

Blender 4.2+ (developed on 5.2).

1. Download `camera_match-<version>.zip` from the [latest release](https://github.com/ardaevin/Blender_CameraMatch/releases/latest). Use the release zip, not GitHub's "Download ZIP" of the source.
2. Blender → Edit → Preferences → Get Extensions → ⌄ → **Install from Disk…** → pick the zip.

## Usage

1. Give the scene camera a background image (Camera properties → Background Images) and make the render resolution match the image. The panel warns about a mismatch and has a one-click fix.
2. Open the **Camera Match** tab in the 3D view sidebar (N) and press **Start Matching**. The view switches to camera view.
3. Drag the handles so each pair of lines follows parallel edges in the image:
   - **1** (orange): lines toward VP1, along the *VP1 Axis*.
   - **2** (blue): lines toward VP2, along the *VP2 Axis*.
   - **3** (magenta): only with *Principal Point → From VP3*.
   - **H**: horizon direction (1-VP mode).
   - **O**: world origin. **R**: reference-distance endpoints, which sit on the chosen axis through O.
4. If an axis comes out flipped, change the sign of *VP1 Axis* / *VP2 Axis*.
5. **Esc** or **Enter** (or *Stop Matching*) finishes.

Controls while matching: **Shift**-drag = precise, **right-click** during a drag = cancel that drag. Each drag is one undo step.

## Limitations

- Assumes no lens distortion. Undistort the plate first.
- One still image, one camera. No multi-frame or multi-image solve.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
