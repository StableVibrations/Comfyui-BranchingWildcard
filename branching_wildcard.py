# branching_wildcard.py

import random

class BranchingWildcardNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mapping":     ("STRING", {"default": "", "multiline": True, "rows": 6}),
                "path":        ("STRING", {"default": ""}),
                "tag_delim":   ("STRING", {"default": " "}),
                "text_delim":  ("STRING", {"default": ", "}),
                "video_delim": ("STRING", {"default": ", "}),
                "seed":        ("INT",    {"default": -1, "min": -1})
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    FUNCTION     = "run"
    CATEGORY     = "Custom/Wildcards"

    def run(self, mapping, path, tag_delim, text_delim, video_delim, seed):
        # --- 1) Parse mapping into tree, desc_map, parent_map ---
        tree = {}          # parent_tag -> list of (child_tag, (desc1, desc2))
        desc_map = {}      # tag -> (desc1, desc2)
        parent_map = {}    # child_tag -> list of parent_tags

        for line in mapping.splitlines():
            if ">" not in line:
                continue
            left, right = [s.strip() for s in line.split(">", 1)]

            # parent: tag[:desc1[:desc2]] — missing means empty string
            parts  = [p.strip() for p in left.split(":", 2)]
            ptag   = parts[0]
            pdesc1 = parts[1] if len(parts) >= 2 else ""
            pdesc2 = parts[2] if len(parts) >= 3 else ""
            desc_map[ptag] = (pdesc1, pdesc2)

            kids = []
            for part in right.split("|"):
                part = part.strip()
                if not part:
                    continue
                cparts = [p.strip() for p in part.split(":", 2)]
                ctag   = cparts[0]
                cdesc1 = cparts[1] if len(cparts) >= 2 else ""
                cdesc2 = cparts[2] if len(cparts) >= 3 else ""
                kids.append((ctag, (cdesc1, cdesc2)))

                desc_map[ctag] = (cdesc1, cdesc2)
                parent_map.setdefault(ctag, []).append(ptag)

            if kids:
                tree.setdefault(ptag, []).extend(kids)

        # --- 2) RNG setup ---
        if seed is None or seed < 0:
            seed = random.randrange(2**32)
        rng = random.Random(seed)

        def backward_fill(start_tag):
            rev = [(start_tag, desc_map[start_tag])]
            cur = start_tag
            while cur in parent_map and parent_map[cur]:
                p = rng.choice(parent_map[cur])
                rev.append((p, desc_map[p]))
                cur = p
            rev.reverse()
            return rev

        # --- 3) Build the path sequence ---
        segments   = [s.strip() for s in path.split("/") if s.strip()]
        path_pairs = []  # list of (tag, (desc1, desc2)) in order

        if segments:
            # wildcard-backfill: "*/leaf1/leaf2…"
            if segments[0] == "*":
                pinned = [t for t in segments[1:] if t in desc_map]
                if not pinned:
                    raise ValueError(f"No valid start found among {segments[1:]}")
                path_pairs = backward_fill(pinned[0])
                cur = path_pairs[-1][0]
                for t in pinned[1:]:
                    kids = [ct for (ct, _) in tree.get(cur, [])]
                    if t not in kids:
                        raise ValueError(f"Pinned '{t}' is not a child of '{cur}'")
                    path_pairs.append((t, desc_map[t]))
                    cur = t
                while cur in tree and tree[cur]:
                    c, d = rng.choice(tree[cur])
                    path_pairs.append((c, d))
                    cur = c

            # forward-pinned: skip to first valid, then stop on invalid
            else:
                start_idx = next((i for i, t in enumerate(segments) if t in desc_map), None)
                if start_idx is None:
                    raise ValueError(f"No valid start found among {segments}")
                filtered = segments[start_idx:]

                cur = None
                for idx, t in enumerate(filtered):
                    if t not in desc_map:
                        break
                    if idx > 0:
                        prev = filtered[idx - 1]
                        kids = [ct for (ct, _) in tree.get(prev, [])]
                        if t not in kids:
                            break
                    path_pairs.append((t, desc_map[t]))
                    cur = t

                while cur in tree and tree[cur]:
                    c, d = rng.choice(tree[cur])
                    path_pairs.append((c, d))
                    cur = c

        else:
            # no path: full random walk from a true root
            parents  = set(tree.keys())
            children = {ct for kids in tree.values() for (ct, _) in kids}
            roots    = list(parents - children)
            if not roots:
                raise ValueError("No root tags found in mapping.")
            cur = rng.choice(roots)
            path_pairs.append((cur, desc_map[cur]))
            while cur in tree and tree[cur]:
                c, d = rng.choice(tree[cur])
                path_pairs.append((c, d))
                cur = c

        # --- 4) Split into tags + descriptions + return ---
        tags   = [tag.replace(" ", "_").lower() for (tag, _) in path_pairs]
        desc1s = [d[0] for (_, d) in path_pairs]
        desc2s = [d[1] for (_, d) in path_pairs]

        tags_str   = tag_delim.join(tags)
        image_str  = text_delim.join(desc1s)
        video_str  = video_delim.join(desc2s)

        return (tags_str, image_str, video_str)


# register
NODE_CLASS_MAPPINGS = {
    "BranchingWildcardNode": BranchingWildcardNode
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "BranchingWildcardNode": "Branching Wildcard"
}
