# branching_wildcard.py

import random
from collections import defaultdict
import folder_paths  # ComfyUI helper for locating model files

class BranchingWildcardNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mapping":       ("STRING",  {"default":"",   "multiline":True, "rows":6}),
                "path":          ("STRING",  {"default":""}),
                "tag_delim":     ("STRING",  {"default":" "}),
                "text_delim":    ("STRING",  {"default":", "}),
                "video_delim":   ("STRING",  {"default":", "}),
                "lora_mapping":  ("STRING",  {"default":"",   "multiline":True, "rows":4}),
                "seed":          ("INT",     {"default":-1,    "min":-1}),
            },
            "optional": {
                "weighting_mode": ("STRING", {
                    "default": "uniform",
                    "options": ["uniform", "depth", "inverse_depth"],
                    "tooltip": "How to weight LoRA strengths based on tag order"
                }),
                "weight_scale":   ("FLOAT",  {"default":1.0, "min":0.0, "step":0.01,
                                             "tooltip":"Global multiplier applied after weighting"}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "WANVIDLORA")
    FUNCTION     = "run"
    CATEGORY     = "Custom/Wildcards"

    def run(
        self,
        mapping: str,
        path: str,
        tag_delim: str,
        text_delim: str,
        video_delim: str,
        lora_mapping: str,
        seed: int,
        weighting_mode: str = "uniform",
        weight_scale: float = 1.0
    ):
        # --- 1) Parse hierarchy & descriptions from `mapping` ---
        tree       = defaultdict(list)
        parent_map = defaultdict(list)
        desc1_map  = defaultdict(list)
        desc2_map  = defaultdict(list)

        for line in mapping.splitlines():
            if ">" not in line:
                continue
            left, right = [s.strip() for s in line.split(">", 1)]
            parents = [p.strip() for p in left.split("|")]

            # collect descriptions for parents
            for ptok in parents:
                parts = [x.strip() for x in ptok.split(":", 2)]
                tag = parts[0]
                if len(parts) >= 2 and parts[1]:
                    desc1_map[tag].append(parts[1])
                if len(parts) >= 3 and parts[2]:
                    desc2_map[tag].append(parts[2])

            # children & their descriptions, and link tree/parent_map
            for child in [c.strip() for c in right.split("|") if c.strip()]:
                parts = [x.strip() for x in child.split(":", 2)]
                tag = parts[0]
                if len(parts) >= 2 and parts[1]:
                    desc1_map[tag].append(parts[1])
                if len(parts) >= 3 and parts[2]:
                    desc2_map[tag].append(parts[2])
                for ptok in parents:
                    ptag = ptok.split(":",1)[0].strip()
                    tree[ptag].append(tag)
                    parent_map[tag].append(ptag)

        # --- 2) Parse `lora_mapping` into tag → [(name, strength, low_mem)] ---
        lora_map = {}
        for line in lora_mapping.splitlines():
            if ":" not in line:
                continue
            tag, models = [s.strip() for s in line.split(":", 1)]
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
                    try:
                        strength = float(raw)
                    except:
                        strength = 1.0
                else:
                    name = fn
                    strength = 1.0

                entries.append((name, strength, low_mem))
            lora_map[tag] = entries

        # --- 3) RNG + path selection helpers ---
        if seed is None or seed < 0:
            seed = random.randrange(2**32)
        rng = random.Random(seed)

        def backward_fill(leaf):
            seq = [leaf]
            cur = leaf
            while parent_map[cur]:
                cur = rng.choice(parent_map[cur])
                seq.insert(0, cur)
            return seq

        segments = [s.strip() for s in path.split("/") if s.strip()]
        path_tags = []

        if segments and segments[0] == "*":
            # wildcard with pinned
            pinned = [t for t in segments[1:] if t in desc1_map or t in desc2_map]
            if not pinned:
                raise ValueError(f"No valid start among {segments[1:]}")
            path_tags = backward_fill(pinned[0])
            cur = path_tags[-1]
            for t in pinned[1:]:
                if t not in tree[cur]:
                    raise ValueError(f"Pinned '{t}' not a child of '{cur}'")
                path_tags.append(t)
                cur = t
            while tree[cur]:
                cur = rng.choice(tree[cur])
                path_tags.append(cur)

        elif segments:
            # explicit path
            idx = next((i for i,t in enumerate(segments)
                        if t in desc1_map or t in desc2_map), None)
            if idx is None:
                raise ValueError(f"No valid start among {segments}")
            filtered = segments[idx:]
            cur = None
            for i, t in enumerate(filtered):
                if t not in desc1_map and t not in desc2_map:
                    break
                if i>0 and t not in tree.get(filtered[i-1], []):
                    break
                path_tags.append(t)
                cur = t
            while cur and tree[cur]:
                cur = rng.choice(tree[cur])
                path_tags.append(cur)

        else:
            # pick a random root
            roots = list(set(tree.keys()) - {c for kids in tree.values() for c in kids})
            if not roots:
                raise ValueError("No root tags found.")
            cur = rng.choice(roots)
            path_tags = [cur]
            while tree[cur]:
                cur = rng.choice(tree[cur])
                path_tags.append(cur)

        # --- 4) Build output strings ---
        tags_str  = tag_delim.join(t.replace(" ", "_").lower() for t in path_tags)
        image_str = text_delim.join(d for t in path_tags for d in desc1_map.get(t, []))
        video_str = video_delim.join(d for t in path_tags for d in desc2_map.get(t, []))

        # --- 5) Compute per-tag weight factors ---
        n = len(path_tags)
        if weighting_mode == "depth":
            factors = [(i+1)/n for i in range(n)]
        elif weighting_mode == "inverse_depth":
            factors = [(n-i)/n for i in range(n)]
        else:  # uniform
            factors = [1.0]*n
        factors = [f * weight_scale for f in factors]

        # --- 6) Build default blocks mapping and collect LoRAs ---
        # only blocks 0–19 enabled by default (blocks 20–39 omitted)
        default_blocks = { f"blocks.{i}.": True for i in range(20) }

        loras = []
        for idx, tag in enumerate(path_tags):
            wf = factors[idx]
            for name, base_strength, low_mem in lora_map.get(tag, []):
                full_path = folder_paths.get_full_path("loras", name)
                loras.append({
                    "path":         full_path,
                    "strength":     base_strength * wf,
                    "name":         name.rsplit(".", 1)[0],
                    "blocks":       default_blocks.copy(),
                    "layer_filter": [],     # no filtering by default
                    "low_mem_load": low_mem
                })

        return (tags_str, image_str, video_str, loras)


# Register for ComfyUI
NODE_CLASS_MAPPINGS = {
    "BranchingWildcardNode": BranchingWildcardNode
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "BranchingWildcardNode": "Branching Wildcard"
}
