# Branching Wildcard (ComfyUI Node)

A hierarchical wildcard + LoRA routing node for ComfyUI.

This node lets you:

- Define **branching prompt trees** with weighted choices.
- Generate **image and video descriptions** from the same branch.
- Attach **different LoRA sets** to each tag:
  - `image_loras` for SD1.5 / SDXL / Illustrious / Flux / Qwen, etc.
  - `wan_loras` for WAN / WAN-powered video workflows.

It’s designed to sit near the front of your workflow and decide, for each run, _which_ character / outfit / camera / motion branch to use, and automatically wire the right text and LoRAs.

---

## Installation

1. Drop `branching_wildcard.py` into your ComfyUI `custom_nodes` folder, for example:

   ```text
   ComfyUI/custom_nodes/branching_wildcard/branching_wildcard.py
   ```

2. Restart ComfyUI.  
3. You should see the node under:

   ```text
   Custom / Wildcards / Branching Wildcard
   ```

---

## Node Overview

**Display name:** `Branching Wildcard`  
**Class:** `BranchingWildcardNode`  

### Inputs (UI order)

**Required**

- `path`  
  String that controls how the node walks the tree:
  - `""` (empty) → pick a random root, then walk down randomly.
  - `root/pose/camera` → follow tags as far as possible, then continue randomly.
  - `*/tagA/tagB` → wildcard start: pick any branch that contains `tagA → tagB`, fill in parents and children randomly around them.

- `mapping`  
  The branching definition and optional descriptions. This is where you define the tree of tags.

- `image_lora_mapping`  
  LoRAs for **image models** (SD1.5 / SDXL / Illustrious / Flux / Qwen, etc.).  
  These are sent out as a `LORA_STACK` from the `image_loras` output.

- `lora_mapping`  
  LoRAs for **WAN / WAN-style video** pipelines.  
  These are sent out as `wan_loras` (type `WANVIDLORA`).

- `seed`  
  - `-1` → random seed each execution.  
  - `>= 0` → deterministic branch selection for that seed.

- `tag_delim`  
  Delimiter for the `tag` output (default: /).

- `text_delim`  
  Delimiter for **Description 1** output (default: `", "`).

- `video_delim`  
  Delimiter for **Description 2** output (default: `", "`).

**Optional**

- `weighting_mode` (`"uniform"`, `"depth"`, `"inverse_depth"`)  
  How LoRA strength is scaled along the branch (explained in detail below).

- `weight_scale` (`float`, default `1.0`)  
  Global multiplier applied to all LoRA strengths after weighting.

---

## Outputs

The node returns:

1. `tag` (`STRING`)  
   All unique tags chosen along the branch, joined with `tag_delim`.  
   Useful for debugging and passing into other nodes.

2. `description 1` (`STRING`)  
   Image-oriented description.  
   This is built from the **first description slot** in your mapping (`desc1`).

3. `description 2` (`STRING`)  
   Video-oriented description.  
   This is built from the **second description slot** in your mapping (`desc2`).

4. `image_loras` (`LORA_STACK`)  
   List of tuples:

   ```python
   [
       (lora_name_or_relative_path, strength_model, strength_clip),
       ...
   ]
   ```

   Plug this into nodes that accept `LORA_STACK`, for example:

   - `LoRA Stack to String` → `CR Apply LoRA stack` / `Apply LoRA stack`
   - Easy Diffusion / Comfyroll LoRA helpers that accept stacks

   The node deliberately passes **names or relative paths**, _not_ full absolute paths.  
   Your downstream nodes resolve them via `folder_paths`.

5. `wan_loras` (`WANVIDLORA`)  
   List of WAN-style LoRA configs (dicts).  
   Feed this directly into your WAN / rgthree WAN LoRA loader.

---

## Mapping Syntax

`mapping` describes the tree structure and optional descriptions for each tag.

General format (per line):

```text
level1 > level2 > level3
```

Within a level you can have alternatives separated by `|`:

```text
root > option1 | option2 | option3
```

You can also attach up to two descriptions per tag:

```text
tag:desc1
tag:desc1:desc2
```

- `desc1` → used for **description 1** (image_prompt).
- `desc2` → used for **description 2** (video_prompt).

### Examples

**Simple hierarchy**

```text
root
root > outfit_casual | outfit_armor
root > camera_close | camera_full
```

**With descriptions**

```text
root:base scene:base scene loop
root > outfit_casual:casual modern clothing:casual outfit for animation
root > outfit_armor:ornate fantasy armor:ornate armor moving with the body
root > camera_close:close-up framing:close camera framing
root > camera_full:full-body shot:full character in frame
```

**Weighted branching**

```text
root > outfit_casual | outfit_armor | outfit_armor | outfit_armor
```

Here, `outfit_armor` appears three times under `root`.  
The node **keeps duplicates** when building the tree, so the choice at this level is:

- `P(outfit_casual) = 1 / 4`
- `P(outfit_armor)  = 3 / 4`

Duplicating an option acts as a **weight**.

---

## Path Syntax

The `path` input controls how the node walks the tree.

### 1. Empty path

```text
path = ""
```

- Pick a random root tag (a tag that is never a child).
- Repeatedly pick a random child at each level (respecting weights).
- Stop at a tag with no children.

### 2. Explicit path

```text
path = "root/outfit_armor"
```

- Try to follow `root → outfit_armor` exactly.
- If the mapping supports those transitions, they become the start of `path_tags`.
- From the last valid tag, continue randomly downward until you hit a leaf.

If the path doesn’t fully match, it follows as far as possible and then drops into random mode.

### 3. Wildcard with pinned tags

```text
path = "*/outfit_armor/camera_close"
```

- Leading `*` means “I don’t care which root or parents you use, as long as you hit this pinned sequence somewhere”.
- The node:
  1. Finds `outfit_armor`, climbs **upward randomly** using `parent_map` to reconstruct a valid ancestor chain to some root.
  2. Enforces `camera_close` as a child of `outfit_armor`.
  3. From there, continues randomly downward if there are further children.

This is useful when you care about certain “middle” tags, but want the rest (parents / deeper children) to be randomized.

---

## LoRA Mapping Syntax

There are two separate LoRA mapping inputs:

- `image_lora_mapping` → `image_loras` (`LORA_STACK`)
- `lora_mapping` → `wan_loras` (`WANVIDLORA`)

Both use the same basic text format:

```text
tag: lora1@strength, lora2@strength:lowmem
```

- `tag` must match one of your mapping tags.
- `lora1`, `lora2` are LoRA **names or relative paths** as seen by ComfyUI.
- `@strength` is optional (`1.0` by default).
- `:lowmem` flag is optional (only meaningful for WAN in this node).

### Image LoRAs (for SD1.5 / SDXL / etc.)

Example:

```text
outfit_armor: illustrious/Armor_Set_A.safetensors@0.9
camera_close: camera_depth_lora.safetensors@0.6
```

The node outputs:

```python
image_loras = [
    ("illustrious/Armor_Set_A.safetensors", 0.9 * factor, 0.9 * factor),
    ("camera_depth_lora.safetensors",       0.6 * factor, 0.6 * factor),
    ...
]
```

You then wire `image_loras` into:

- `LoRA Stack to String` → `Apply LoRA stack`, or
- Any other node that accepts `LORA_STACK`.

### WAN LoRAs

Example:

```text
outfit_armor: wan_armor_motion@1.0
camera_close: wan_camera_shake@0.7:lowmem
```

Each tag’s LoRAs become entries like:

```python
{
    "path":         full_path_resolved_by_folder_paths,
    "strength":     base_strength * factor,
    "name":         "wan_armor_motion",
    "blocks":       {...},
    "layer_filter": [],
    "low_mem_load": True/False,
}
```

Send `wan_loras` into your WAN / rgthree LoRA loader for video.

---

## LoRA Weighting Along the Branch

Once a branch is chosen, you have something like:

```python
path_tags = ["root", "outfit_armor", "camera_close", "character_elven"]
```

For each tag in `path_tags`, the node:

1. Looks up LoRAs for that tag.
2. Computes a **position-based factor**.
3. Multiplies the mapped strength by that factor (and `weight_scale`).

### Factor calculation

Let `n = len(path_tags)`.

- `weighting_mode = "uniform"` (default):

  ```python
  factors = [1.0] * n
  ```

  LoRAs use exactly the strengths from your mappings (only affected by `weight_scale`).

- `weighting_mode = "depth"`:

  ```python
  factors[i] = (i + 1) / n
  ```

  For a 4-tag path:

  ```text
  root            → 0.25
  outfit_armor    → 0.50
  camera_close    → 0.75
  character_elven → 1.00
  ```

  Deeper tags (more specific) get stronger LoRA weights.

- `weighting_mode = "inverse_depth"`:

  ```python
  factors[i] = (n - i) / n
  ```

  For the same path:

  ```text
  root            → 1.00
  outfit_armor    → 0.75
  camera_close    → 0.50
  character_elven → 0.25
  ```

  Higher-level tags (more global style) get stronger weights.

Finally:

```python
factors = [f * weight_scale for f in factors]
actual_strength = base_strength * factor
```

If you don’t care about this behavior, stick with:

- `weighting_mode = "uniform"`
- `weight_scale = 1.0`

and the node will use your mapping strengths as-is.

---

## Typical Usage Patterns

- Use `description 1` as your **image prompt fragment**.
- Use `description 2` as your **video / motion prompt fragment** for WAN.
- Connect:
  - `image_loras` → your SD LoRA stack pipeline.
  - `wan_loras`   → your WAN/rgthree LoRA loader.

Drive it all from a single `mapping` file so your images, videos, and LoRAs stay consistent and in sync.
