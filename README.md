# BranchingWildcard Node for ComfyUI

A custom ComfyUI node that generates two parallel “descriptions” (for image & video prompts) by traversing a user-defined wildcard tree with both forward-pinned and wildcard-backfill behavior.

---

## Features

- **Wildcard backfill**  
  Use `*` in your path to start at a random leaf, backfill up to the root, then descend randomly.

- **Forward-pinned**  
  Specify a chain of required tags; unknown prefixes are ignored.

- **Dual descriptions**  
  Every tag can have two descriptions, one for image prompts and one for video prompts.

- **Reproducible**  
  Supply a `seed` to recreate the same tag sequence.

---

## Installation

1. **Place the node file**  
   Copy `branching_wildcard.py` into your ComfyUI `nodes/Custom/` directory. For example:

       cp branching_wildcard.py ~/ComfyUI/nodes/Custom/

2. **Restart ComfyUI**  
   Relaunch your ComfyUI server. You’ll find **Branching Wildcard** under **Custom → Wildcards** in the Node Library.

---

## Usage in a Flow

1. **Add** the **Branching Wildcard** node to your canvas.  
2. **Connect** its outputs into downstream nodes (e.g. a Prompt Combiner or a Text Encoder).  
3. **Configure** its inputs:

   | Input Name   | Type    | Description                                        |
   |--------------|---------|----------------------------------------------------|
   | mapping      | STRING  | Tag-tree definition (multiline)                    |
   | path         | STRING  | `/`-delimited sequence; may start with `*`         |
   | tag_delim    | STRING  | Separator for returned tag list (default: space)   |
   | text_delim   | STRING  | Separator for “image” descriptions (default: `, `) |
   | video_delim  | STRING  | Separator for “video” descriptions (default: `, `) |
   | seed         | INT     | RNG seed (`-1` for random each run)                |

4. **Interpret** its three outputs:

   | Output Index | Name           | Description                                       |
   |--------------|----------------|---------------------------------------------------|
   | 0            | tags           | Joined tag list (using `tag_delim`)               |
   | 1            | image_prompt   | Joined first descriptions (using `text_delim`)    |
   | 2            | video_prompt   | Joined second descriptions (using `video_delim`)  |

---

## Mapping & Path Syntax

### 1. Mapping

Define parent→children relationships, one per line:

    ParentTag:desc1:desc2 > ChildA:descA1:descA2 | ChildB:descB1:descB2

- **ParentTag** may include two colon-separated descriptions (`desc1` for image prompts, `desc2` for video prompts).  
- **Children** are separated by `|`, each optionally with their own dual descriptions.

### 2. Path

- **Empty**: picks a random root and descends randomly.  
- **Forward-pinned** (e.g. `Mammal/Cat`): finds `Mammal`, then `Cat`, then random descent.  
- **Wildcard** (e.g. `*/Dog`): backfills from a random leaf among `[Dog,…]` to root, then includes `Dog`, then descends.

---

## Example

**Mapping**:

    Animal:animal:creature > Mammal:mammal:furred | Bird:bird:winged
    Mammal > Dog:dog:puppy | Cat:cat:kitten
  

**Path**:

    */Dog

**Possible Outputs**:

- **tags**: `Animal Mammal Dog`  
- **image_prompt**: `animal, mammal, dog`  
- **video_prompt**: `creature, furred, puppy`

---
