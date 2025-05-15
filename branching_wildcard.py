# branching_wildcard.py

import random
from collections import defaultdict
import folder_paths  # ComfyUI utility for locating model files

class BranchingWildcardNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mapping":      ("STRING",  {"default":"",   "multiline":True, "rows":6}),
                "path":         ("STRING",  {"default":""}),
                "tag_delim":    ("STRING",  {"default":" "}),
                "text_delim":   ("STRING",  {"default":", "}),
                "video_delim":  ("STRING",  {"default":", "}),
                "lora_mapping": ("STRING",  {"default":"",   "multiline":True, "rows":4}),
                "seed":         ("INT",     {"default":-1,    "min":-1}),
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
        seed: int
    ):
        # --- 1) Parse mapping into hierarchy + descriptions ---
        tree       = defaultdict(list)
        parent_map = defaultdict(list)
        desc1_map  = defaultdict(list)
        desc2_map  = defaultdict(list)

        for line in mapping.splitlines():
            if ">" not in line: continue
            left, right = [s.strip() for s in line.split(">", 1)]

            # grouped parents
            parent_tokens = [p.strip() for p in left.split("|")]
            for ptok in parent_tokens:
                parts = [x.strip() for x in ptok.split(":", 2)]
                tag   = parts[0]
                if len(parts) >= 2 and parts[1]:
                    desc1_map[tag].append(parts[1])
                if len(parts) >= 3 and parts[2]:
                    desc2_map[tag].append(parts[2])

            # children
            for part in [c.strip() for c in right.split("|") if c.strip()]:
                parts = [x.strip() for x in part.split(":", 2)]
                tag   = parts[0]
                if len(parts) >= 2 and parts[1]:
                    desc1_map[tag].append(parts[1])
                if len(parts) >= 3 and parts[2]:
                    desc2_map[tag].append(parts[2])
                for ptok in parent_tokens:
                    ptag = ptok.split(":",1)[0].strip()
                    tree[ptag].append(tag)
                    parent_map[tag].append(ptag)

        # --- 2) Parse lora_mapping into dict[tag -> list of (name, strength, low_mem)] ---
        lora_map = {}
        for line in lora_mapping.splitlines():
            if ":" not in line: continue
            tag, models = [s.strip() for s in line.split(":", 1)]
            entries = []
            for fn in models.replace("|", ",").split(","):
                fn = fn.strip()
                if not fn: continue

                # low-mem suffix
                low_mem = False
                if fn.lower().endswith(":lowmem"):
                    low_mem = True
                    fn = fn[:-len(":lowmem")].strip()

                # strength suffix
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

        # --- 3) RNG setup + backward helper ---
        if seed is None or seed < 0:
            seed = random.randrange(2**32)
        rng = random.Random(seed)

        def backward_fill(leaf):
            seq = [leaf]
            cur = leaf
            while cur in parent_map and parent_map[cur]:
                cur = rng.choice(parent_map[cur])
                seq.append(cur)
            return list(reversed(seq))

        # --- 4) Build pinned + random path_tags ---
        segments = [s.strip() for s in path.split("/") if s.strip()]
        path_tags = []

        if segments and segments[0] == "*":
            pinned = [t for t in segments[1:] if t in desc1_map or t in desc2_map]
            if not pinned:
                raise ValueError(f"No valid start among {segments[1:]}")
            path_tags = backward_fill(pinned[0])
            cur = path_tags[-1]
            for t in pinned[1:]:
                if t not in tree.get(cur, []):
                    raise ValueError(f"Pinned '{t}' not a child of '{cur}'")
                path_tags.append(t)
                cur = t
            while cur in tree and tree[cur]:
                cur = rng.choice(tree[cur])
                path_tags.append(cur)

        elif segments:
            idx = next((i for i, t in enumerate(segments)
                        if t in desc1_map or t in desc2_map), None)
            if idx is None:
                raise ValueError(f"No valid start among {segments}")
            filtered = segments[idx:]
            cur = None
            for i, t in enumerate(filtered):
                if not (t in desc1_map or t in desc2_map):
                    break
                if i > 0 and t not in tree.get(filtered[i-1], []):
                    break
                path_tags.append(t)
                cur = t
            while cur in tree and tree[cur]:
                cur = rng.choice(tree[cur])
                path_tags.append(cur)

        else:
            parents  = set(tree.keys())
            children = {c for kids in tree.values() for c in kids}
            roots    = list(parents - children)
            if not roots:
                raise ValueError("No root tags found.")
            cur = rng.choice(roots)
            path_tags = [cur]
            while cur in tree and tree[cur]:
                cur = rng.choice(tree[cur])
                path_tags.append(cur)

        # filter out any None
        path_tags = [t for t in path_tags if isinstance(t, str)]

        # --- 5) Assemble outputs ---

        # tags
        tags_str = tag_delim.join(t.replace(" ", "_").lower() for t in path_tags)

        # image descriptions
        image_list = []
        for t in path_tags:
            image_list.extend(desc1_map.get(t, []))
        image_str = text_delim.join(image_list)

        # video descriptions
        video_list = []
        for t in path_tags:
            video_list.extend(desc2_map.get(t, []))
        video_str = video_delim.join(video_list)

        # direct WANVIDLORA list, with default blocks 0–19 True, 20–39 False
        default_blocks = [True]*20 + [False]*20
        loras = []
        for t in path_tags:
            for name, strength, low_mem in lora_map.get(t, []):
                full_path = folder_paths.get_full_path("loras", name)
                loras.append({
                    "path":         full_path,
                    "strength":     strength,
                    "name":         name.rsplit(".", 1)[0],
                    "blocks":       default_blocks,
                    "low_mem_load": low_mem
                })

        return (tags_str, image_str, video_str, loras)


# register
NODE_CLASS_MAPPINGS = {
    "BranchingWildcardNode": BranchingWildcardNode
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "BranchingWildcardNode": "Branching Wildcard"
}
