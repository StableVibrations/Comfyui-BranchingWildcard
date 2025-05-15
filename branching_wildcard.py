# branching_wildcard.py

import random
from collections import defaultdict

class BranchingWildcardNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mapping":     ("STRING", {"default":"", "multiline":True, "rows":6}),
                "path":        ("STRING", {"default":""}),
                "tag_delim":   ("STRING", {"default":" "}),
                "text_delim":  ("STRING", {"default":", "}),
                "video_delim": ("STRING", {"default":", "}),
                "seed":        ("INT",    {"default":-1, "min":-1})
            }
        }

    RETURN_TYPES = ("STRING","STRING","STRING")
    FUNCTION     = "run"
    CATEGORY     = "Custom/Wildcards"

    def run(self, mapping, path, tag_delim, text_delim, video_delim, seed):
        # --- 1) Parse mapping into tree, reverse map, and two desc-maps ---
        tree       = defaultdict(list)   # parent_tag -> [child_tag, ...]
        parent_map = defaultdict(list)   # child_tag  -> [parent_tag, ...]
        desc1_map  = defaultdict(list)   # tag        -> [desc1, ...]
        desc2_map  = defaultdict(list)   # tag        -> [desc2, ...]

        for line in mapping.splitlines():
            if ">" not in line:
                continue
            left, right = [s.strip() for s in line.split(">",1)]

            # left may list multiple parents separated by '|'
            parent_tokens = [p.strip() for p in left.split("|")]
            for ptok in parent_tokens:
                # each token may also carry desc1 and/or desc2
                pparts = [x.strip() for x in ptok.split(":",2)]
                ptag   = pparts[0]
                pdesc1 = pparts[1] if len(pparts)>=2 else ""
                pdesc2 = pparts[2] if len(pparts)>=3 else ""
                if pdesc1:
                    desc1_map[ptag].append(pdesc1)
                if pdesc2:
                    desc2_map[ptag].append(pdesc2)

            # parse children once, then assign under each parent
            child_specs = [c.strip() for c in right.split("|") if c.strip()]
            for part in child_specs:
                cparts = [x.strip() for x in part.split(":",2)]
                ctag   = cparts[0]
                cdesc1 = cparts[1] if len(cparts)>=2 else ""
                cdesc2 = cparts[2] if len(cparts)>=3 else ""
                if cdesc1:
                    desc1_map[ctag].append(cdesc1)
                if cdesc2:
                    desc2_map[ctag].append(cdesc2)
                # now wire up this child under *each* parent
                for ptok in parent_tokens:
                    pparts = [x.strip() for x in ptok.split(":",2)]
                    ptag = pparts[0]
                    tree[ptag].append(ctag)
                    parent_map[ctag].append(ptag)

        # --- 2) RNG setup ---
        if seed is None or seed<0:
            seed = random.randrange(2**32)
        rng = random.Random(seed)

        # helper: from a leaf, walk *up* via parent_map to a root
        def backward_fill(leaf):
            seq = [leaf]
            cur = leaf
            while cur in parent_map and parent_map[cur]:
                cur = rng.choice(parent_map[cur])
                seq.append(cur)
            return list(reversed(seq))

        # --- 3) Build the pinned + random path (list of tags) ---
        segments = [s.strip() for s in path.split("/") if s.strip()]
        path_tags = []

        if segments:
            if segments[0]=="*":
                # wildcard‐backfill
                pinned = [t for t in segments[1:] if t in desc1_map or t in desc2_map]
                if not pinned:
                    raise ValueError(f"No valid start in {segments[1:]}")
                path_tags = backward_fill(pinned[0])
                cur = path_tags[-1]
                for t in pinned[1:]:
                    if t not in tree.get(cur,[]):
                        raise ValueError(f"Pinned '{t}' not child of '{cur}'")
                    path_tags.append(t)
                    cur = t
                while cur in tree and tree[cur]:
                    cur = rng.choice(tree[cur])
                    path_tags.append(cur)
            else:
                # forward-pinned: skip to first known, then consume while valid
                idx = next((i for i,t in enumerate(segments)
                            if t in desc1_map or t in desc2_map), None)
                if idx is None:
                    raise ValueError(f"No valid start in {segments}")
                filtered = segments[idx:]
                cur = None
                for i,t in enumerate(filtered):
                    if not (t in desc1_map or t in desc2_map):
                        break
                    if i>0:
                        prev=filtered[i-1]
                        if t not in tree.get(prev,[]):
                            break
                    path_tags.append(t)
                    cur = t
                while cur in tree and tree[cur]:
                    cur = rng.choice(tree[cur])
                    path_tags.append(cur)
        else:
            # no path: random from a root
            parents  = set(tree.keys())
            children = {c for kids in tree.values() for c in kids}
            roots    = list(parents - children)
            if not roots:
                raise ValueError("No root tags found.")
            cur = rng.choice(roots)
            path_tags.append(cur)
            while cur in tree and tree[cur]:
                cur = rng.choice(tree[cur])
                path_tags.append(cur)

        # --- 4) Build outputs ---
        # tags (always include every tag encountered)
        tags_str = tag_delim.join(t.replace(" ","_").lower() for t in path_tags)

        # image descr (d1): collect in order, but only for tags on the final path
        image_list = []
        for t in path_tags:
            image_list.extend(desc1_map.get(t,[]))
        image_str = text_delim.join(image_list)

        # video descr (d2): likewise
        video_list = []
        for t in path_tags:
            video_list.extend(desc2_map.get(t,[]))
        video_str = video_delim.join(video_list)

        return (tags_str, image_str, video_str)


# register
NODE_CLASS_MAPPINGS = {
    "BranchingWildcardNode": BranchingWildcardNode
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "BranchingWildcardNode": "Branching Wildcard"
}
