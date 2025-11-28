# branching_wildcard.py

import random
from collections import defaultdict
import folder_paths  # ComfyUI helper for locating model files


class BranchingWildcardNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                # Path selector first
                "path":          ("STRING",  {"default": ""}),
                # Main branching / mapping definition
                "mapping":       ("STRING",  {"default": "", "multiline": True, "rows": 6}),
                # Image LoRAs for SD1.5 / SDXL / Illustrious / Flux / etc.
                "image_lora_mapping": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "rows": 4,
                    "tooltip": "LoRAs for image models, e.g. tag: my_lora@0.8"
                }),
                # WAN / video LoRAs
                "lora_mapping":  ("STRING",  {
                    "default": "",
                    "multiline": True,
                    "rows": 4,
                    "tooltip": "LoRAs for WAN / video, e.g. tag: wan_lora@1.0"
                }),
                "seed":          ("INT",     {"default": -1, "min": -1, "max": 2**31 - 1}),
                # Delimiters at the bottom
                "tag_delim":     ("STRING",  {"default": " "}),
                "text_delim":    ("STRING",  {"default": ", "}),
                "video_delim":   ("STRING",  {"default": ", "}),
            },
            "optional": {
                "weighting_mode": ("STRING", {
                    "default": "uniform",
                    "tooltip": "uniform = as-is, depth = stronger deeper in branch, inverse_depth = stronger near root"
                }),
                "weight_scale":   ("FLOAT",  {
                    "default": 1.0,
                    "min": 0.0,
                    "step": 0.01,
                    "tooltip": "Global multiplier applied after weighting"
                }),
            }
        }

    # tag, description 1, description 2, image LoRAs, WAN LoRAs
    RETURN_TYPES = ("STRING", "STRING", "STRING", "LORA_STACK", "WANVIDLORA")
    RETURN_NAMES = ("tag", "description 1", "description 2", "image_loras", "wan_loras")
    FUNCTION     = "run"
    CATEGORY     = "Custom/Wildcards"

    def run(
        self,
        path: str,
        mapping: str,
        image_lora_mapping: str,
        lora_mapping: str,
        seed: int,
        tag_delim: str,
        text_delim: str,
        video_delim: str,
        weighting_mode: str = "uniform",
        weight_scale: float = 1.0,
    ):
        # --- 1) Parse hierarchy & descriptions from `mapping` ---
        tree       = defaultdict(list)   # parent -> [child, child, ...] (duplicates kept for weighting)
        parent_map = defaultdict(list)   # child  -> [parent, parent, ...]
        desc1_map  = defaultdict(list)   # tag   -> [image prompt fragments]
        desc2_map  = defaultdict(list)   # tag   -> [video prompt fragments]

        for line in mapping.splitlines():
            if ">" not in line:
                continue

            segments = [seg.strip() for seg in line.split(">") if seg.strip()]
            if not segments:
                continue
            levels = [[p.strip() for p in seg.split("|") if p.strip()] for seg in segments]

            # Connect each level to the next
            for i in range(len(levels) - 1):
                parents = levels[i]
                children = levels[i + 1]

                for child in children:
                    parts = [x.strip() for x in child.split(":", 2)]
                    tag = parts[0]
                    if not tag:
                        continue
                    if len(parts) >= 2 and parts[1]:
                        desc1_map[tag].append(parts[1])
                    if len(parts) >= 3 and parts[2]:
                        desc2_map[tag].append(parts[2])

                    for ptok in parents:
                        ptag = ptok.split(":", 1)[0].strip()
                        if not ptag:
                            continue
                        # KEEP duplicates so repeated children weight probabilities
                        tree[ptag].append(tag)
                        parent_map[tag].append(ptag)

                # Also collect descs for parent tokens themselves
                for ptok in parents:
                    parts = [x.strip() for x in ptok.split(":", 2)]
                    tag = parts[0]
                    if not tag:
                        continue
                    if len(parts) >= 2 and parts[1]:
                        desc1_map[tag].append(parts[1])
                    if len(parts) >= 3 and parts[2]:
                        desc2_map[tag].append(parts[2])

            # Final level descriptions (if a line ends without explicit children)
            parents = levels[-1]
            for ptok in parents:
                parts = [x.strip() for x in ptok.split(":", 2)]
                tag = parts[0]
                if not tag:
                    continue
                if len(parts) >= 2 and parts[1]:
                    desc1_map[tag].append(parts[1])
                if len(parts) >= 3 and parts[2]:
                    desc2_map[tag].append(parts[2])

        # --- 2) Parse lora mappings into tag → [(name, strength, low_mem)] ---
        def parse_lora_mapping_text(text: str):
            result = {}
            for line in text.splitlines():
                if ":" not in line:
                    continue
                tag, models = [s.strip() for s in line.split(":", 1)]
                if not tag:
                    continue
                entries = []
                for fn in models.replace("|", ",").split(","):
                    fn = fn.strip()
                    if not fn:
                        continue

                    low_mem = fn.lower().endswith(":lowmem")
                    if low_mem:
                        fn = fn[:-len(":lowmem")].strip()

                    if "@" in fn:
                        name, raw = fn.rsplit("@", 1)
                        name = name.strip()
                        try:
                            strength = float(raw)
                        except Exception:
                            strength = 1.0
                    else:
                        name = fn
                        strength = 1.0

                    if not name:
                        continue
                    entries.append((name, strength, low_mem))
                if entries:
                    result[tag] = entries
            return result

        image_lora_map = parse_lora_mapping_text(image_lora_mapping)
        wan_lora_map   = parse_lora_mapping_text(lora_mapping)

        # --- 3) RNG setup ---
        if seed is None or seed < 0:
            seed = random.randrange(2**32)
        rng = random.Random(seed)

        # --- 4) Path resolution helpers ---
        def backward_fill(leaf_tag: str):
            seq = [leaf_tag]
            cur = leaf_tag
            while parent_map.get(cur):
                cur = rng.choice(parent_map[cur])
                seq.insert(0, cur)
            return seq

        segments = [s.strip() for s in path.split("/") if s.strip()]
        path_tags = []

        if segments and segments[0] == "*":
            # wildcard with pinned tags after "*"
            pinned = [t for t in segments[1:] if t in desc1_map or t in desc2_map]
            if not pinned:
                raise ValueError(f"No valid start among {segments[1:]}")
            path_tags = backward_fill(pinned[0])
            cur = path_tags[-1]
            # enforce the rest of the pinned sequence as children
            for t in pinned[1:]:
                if t not in tree.get(cur, []):
                    raise ValueError(f"Pinned '{t}' is not a child of '{cur}' in mapping.")
                path_tags.append(t)
                cur = t
            # then continue randomly downward
            while tree.get(cur):
                options = tree[cur]  # duplicates kept → weighted random
                cur = rng.choice(options)
                path_tags.append(cur)

        elif segments:
            # explicit path: follow as far as it matches, then random-walk
            idx = None
            for i, t in enumerate(segments):
                if t in desc1_map or t in desc2_map:
                    idx = i
                    break
            if idx is None:
                raise ValueError(f"No valid start among path segments: {segments}")
            filtered = segments[idx:]
            cur = None
            for i, t in enumerate(filtered):
                if t not in desc1_map and t not in desc2_map:
                    break
                if i > 0 and t not in tree.get(filtered[i - 1], []):
                    break
                path_tags.append(t)
                cur = t
            while cur and tree.get(cur):
                options = tree[cur]
                cur = rng.choice(options)
                path_tags.append(cur)

        else:
            # random root with no explicit path
            all_parents = set(tree.keys())
            all_children = set(c for kids in tree.values() for c in kids)
            roots = list(all_parents - all_children)
            if not roots:
                raise ValueError("No root tags found in mapping.")
            cur = rng.choice(roots)
            path_tags = [cur]
            while tree.get(cur):
                options = tree[cur]
                cur = rng.choice(options)
                path_tags.append(cur)

        # --- 5) Build output strings (deduped tags, but all descs kept) ---
        def dedup_preserve(seq):
            seen = set()
            out = []
            for x in seq:
                if x not in seen:
                    seen.add(x)
                    out.append(x)
            return out

        used_tags = dedup_preserve(path_tags)
        tag_str = tag_delim.join(used_tags)

        desc1_tokens = []
        desc2_tokens = []
        for t in used_tags:
            if desc1_map.get(t):
                desc1_tokens.extend(desc1_map[t])
            if desc2_map.get(t):
                desc2_tokens.extend(desc2_map[t])

        desc1_str = text_delim.join(dedup_preserve(desc1_tokens))
        desc2_str = video_delim.join(dedup_preserve(desc2_tokens))

        # --- 6) Compute per-tag weight factors for LoRAs ---
        n = len(path_tags)
        if n == 0:
            return (tag_str, desc1_str, desc2_str, [], [])

        if weighting_mode == "depth":
            factors = [(i + 1) / n for i in range(n)]
        elif weighting_mode == "inverse_depth":
            factors = [(n - i) / n for i in range(n)]
        else:  # "uniform"
            factors = [1.0] * n

        factors = [f * weight_scale for f in factors]

        # --- 7) Build image LoRA stack (LORA_STACK: (name, model_strength, clip_strength)) ---
        image_loras = []
        for idx, tag in enumerate(path_tags):
            wf = factors[idx]
            for name, base_strength, _low_mem in image_lora_map.get(tag, []):
                strength = base_strength * wf
                image_loras.append((name, strength, strength))

        # --- 8) Build WAN LoRA stack (WANVIDLORA) ---
        default_blocks = {f"blocks.{i}.": True for i in range(40)}
        wan_loras = []
        for idx, tag in enumerate(path_tags):
            wf = factors[idx]
            for name, base_strength, low_mem in wan_lora_map.get(tag, []):
                full_path = folder_paths.get_full_path("loras", name)
                wan_loras.append({
                    "path":         full_path,
                    "strength":     base_strength * wf,
                    "name":         name.rsplit(".", 1)[0],
                    "blocks":       default_blocks.copy(),
                    "layer_filter": [],
                    "low_mem_load": low_mem,
                })

        return (tag_str, desc1_str, desc2_str, image_loras, wan_loras)


# Register for ComfyUI
NODE_CLASS_MAPPINGS = {
    "BranchingWildcardNode": BranchingWildcardNode
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "BranchingWildcardNode": "Branching Wildcard"
}
