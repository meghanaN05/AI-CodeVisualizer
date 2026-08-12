"""Rule-based animation planner — converts IR into structured scene plans."""

from __future__ import annotations

from typing import Any

from animation_schema import AnimationPlan, SceneAction

DEFAULT_TREE: dict[str, Any] = {
    "value": 10,
    "left": {
        "value": 5,
        "left": {"value": 3},
        "right": {"value": 7},
    },
    "right": {"value": 20},
}

DEFAULT_SORT_ARRAY = [64, 34, 25, 12, 22, 11, 90]
DEFAULT_SEARCH_ARRAY = [2, 5, 8, 12, 16, 23, 38, 56, 72, 91]


def plan_from_ir(ir: dict[str, Any]) -> AnimationPlan:
    algorithm = ir.get("algorithm") or "generic"
    data_structures = ir.get("data_structures") or []
    concepts = ir.get("concepts") or []

    if algorithm == "twitter_design" or "twitter_design" in concepts:
        return _plan_twitter_design(ir)
    if algorithm == "lru_cache" or "lru_cache" in concepts:
        return _plan_lru_cache(ir)
    if algorithm in {"heap_hashmap_composite"} or (
        "hash_map" in data_structures and "heap" in data_structures
    ):
        return _plan_heap_hashmap(ir)
    if algorithm == "trie" or "trie" in data_structures:
        return _plan_trie(ir)
    if algorithm == "union_find" or "union_find" in data_structures:
        return _plan_union_find(ir)
    if algorithm == "dynamic_programming" or "dynamic_programming" in concepts:
        return _plan_dynamic_programming(ir)
    if ir.get("classes") and len(ir.get("methods") or []) > 0:
        return _plan_class_design(ir)

    if algorithm == "inorder_traversal":
        return _plan_inorder(ir)
    if algorithm == "preorder_traversal":
        return _plan_preorder(ir)
    if algorithm == "postorder_traversal":
        return _plan_postorder(ir)
    if algorithm == "binary_search":
        return _plan_binary_search(ir)
    if algorithm == "bubble_sort":
        return _plan_bubble_sort(ir)
    if algorithm == "selection_sort":
        return _plan_selection_sort(ir)
    if algorithm == "insertion_sort":
        return _plan_insertion_sort(ir)
    if algorithm == "bfs":
        return _plan_graph_traversal(ir, "BFS")
    if algorithm == "dfs":
        return _plan_graph_traversal(ir, "DFS")
    if algorithm == "recursion":
        return _plan_recursion(ir)
    if "binary_tree" in data_structures:
        return _plan_tree_generic(ir)
    if "array" in data_structures or ir.get("arrays"):
        return _plan_array(ir)
    if "graph" in data_structures:
        return _plan_graph_generic(ir)
    if "hash_map" in data_structures:
        return _plan_hashmap(ir)
    if "heap" in data_structures:
        return _plan_heap(ir)
    if "stack" in data_structures and "queue" not in data_structures:
        return _plan_stack_demo(ir)

    return _plan_dsa_overview(ir)


def _class_name(ir: dict[str, Any]) -> str:
    classes = ir.get("classes") or []
    return classes[0]["name"] if classes else "Solution"


def _method_names(ir: dict[str, Any]) -> list[str]:
    return [m.get("name", "") for m in ir.get("methods") or [] if m.get("name")]


def _plan_twitter_design(ir: dict[str, Any]) -> AnimationPlan:
    class_name = _class_name(ir)
    methods = _method_names(ir) or [
        "postTweet",
        "getNewsFeed",
        "follow",
        "unfollow",
    ]
    scenes: list[SceneAction] = [
        SceneAction(action="show_title", text=f"{class_name} — DSA Design"),
        SceneAction(
            action="show_class_methods",
            text=class_name,
            nodes=methods,
            caption="Object-oriented design using hash maps, heap, and graphs",
        ),
        SceneAction(
            action="show_hashmap",
            text="tweets",
            values=[["user 1", "[(t0,101), (t1,102)]"], ["user 2", "[(t0,201)]"]],
            caption="unordered_map stores each user's tweets as (timestamp, tweetId) pairs",
        ),
        SceneAction(
            action="hashmap_insert",
            text="tweets",
            label="user 1 → (t2, 103)",
            caption="postTweet(userId, tweetId): append {time++, tweetId} to tweets[userId]",
        ),
        SceneAction(
            action="show_graph",
            nodes=["User1", "User2", "User3"],
            caption="follows map: user → set of followees (graph adjacency)",
        ),
        SceneAction(
            action="visit_node",
            node="User1",
            caption="follow(1, 2): add edge User1 → User2",
        ),
        SceneAction(
            action="show_heap",
            values=[("(t2,103)", 103), ("(t1,102)", 102), ("(t0,201)", 201)],
            caption="getNewsFeed: merge tweets into max-heap by timestamp",
        ),
        SceneAction(
            action="heap_push",
            label="(t2, 103)",
            caption="Push own + followee tweets into priority_queue",
        ),
        SceneAction(
            action="heap_pop",
            label="103",
            caption="Pop top 10 most recent tweet IDs for the feed",
        ),
        SceneAction(
            action="create_array",
            values=[103, 102, 201],
            caption="Result: 10 most recent tweets from user + followees",
        ),
    ]
    for method in methods:
        scenes.append(
            SceneAction(
                action="show_method_flow",
                text=method,
                caption=f"Method {method}() — core logic from your implementation",
            )
        )
    scenes.append(SceneAction(action="show_caption", text=f"{class_name} visualization complete"))
    return AnimationPlan(
        algorithm="twitter_design",
        title=f"{class_name} Design",
        data_structure="hash_map",
        description="Hash map + priority queue + follow graph",
        scenes=scenes,
    )


def _plan_class_design(ir: dict[str, Any]) -> AnimationPlan:
    class_name = _class_name(ir)
    methods = _method_names(ir)
    structures = ir.get("data_structures") or []
    scenes: list[SceneAction] = [
        SceneAction(action="show_title", text=f"{class_name} — DSA Visualization"),
        SceneAction(
            action="show_class_methods",
            text=class_name,
            nodes=methods,
            caption=f"Uses: {', '.join(structures) if structures else 'multiple data structures'}",
        ),
    ]

    if "hash_map" in structures:
        scenes.append(
            SceneAction(
                action="show_hashmap",
                text="map",
                values=[["key A", "value 1"], ["key B", "value 2"]],
                caption="Hash map for O(1) lookup and storage",
            )
        )
    if "heap" in structures:
        scenes.append(
            SceneAction(
                action="show_heap",
                values=[("item", 10), ("item", 7), ("item", 3)],
                caption="Priority queue / heap for ordered access",
            )
        )
    if "graph" in structures or "set" in structures:
        scenes.append(
            SceneAction(
                action="show_graph",
                nodes=["A", "B", "C"],
                caption="Graph / adjacency for relationships",
            )
        )
    if "array" in structures:
        scenes.append(
            SceneAction(action="create_array", values=[1, 2, 3, 4, 5], caption="Array operations")
        )
    if "binary_tree" in structures:
        scenes.append(SceneAction(action="show_tree", tree=DEFAULT_TREE, caption="Tree structure"))

    for method in methods[:6]:
        scenes.append(
            SceneAction(
                action="show_method_flow",
                text=method,
                caption=f"Execute {method}() step by step",
            )
        )

    scenes.append(SceneAction(action="show_caption", text="Class-based DSA design complete"))
    return AnimationPlan(
        algorithm=ir.get("algorithm") or "class_design",
        title=f"{class_name} Design",
        data_structure=structures[0] if structures else "composite",
        description="Multi-structure class design visualization",
        scenes=scenes,
    )


def _plan_heap_hashmap(ir: dict[str, Any]) -> AnimationPlan:
    return _plan_twitter_design(ir)


def _plan_hashmap(ir: dict[str, Any]) -> AnimationPlan:
    scenes: list[SceneAction] = [
        SceneAction(action="show_title", text="Hash Map Visualization"),
        SceneAction(
            action="show_hashmap",
            text="map",
            values=[["key 1", "10"], ["key 2", "20"], ["key 3", "30"]],
            caption="Hash map: O(1) average insert, lookup, delete",
        ),
        SceneAction(action="hashmap_insert", text="map", label="key 4 → 40", caption="Insert key-value pair"),
        SceneAction(action="hashmap_insert", text="map", label="lookup key 2", caption="Lookup returns 20"),
    ]
    return AnimationPlan(
        algorithm="hash_map",
        title="Hash Map",
        data_structure="hash_map",
        scenes=scenes,
    )


def _plan_heap(ir: dict[str, Any]) -> AnimationPlan:
    scenes: list[SceneAction] = [
        SceneAction(action="show_title", text="Heap / Priority Queue"),
        SceneAction(
            action="show_heap",
            values=[("(10, id1)", 10), ("(7, id2)", 7), ("(3, id3)", 3)],
            caption="Max-heap: largest element at top",
        ),
        SceneAction(action="heap_push", label="(12, id4)", caption="push — O(log n)"),
        SceneAction(action="heap_pop", label="12", caption="pop — extract maximum"),
    ]
    return AnimationPlan(
        algorithm="heap",
        title="Priority Queue",
        data_structure="heap",
        scenes=scenes,
    )


def _plan_lru_cache(ir: dict[str, Any]) -> AnimationPlan:
    scenes: list[SceneAction] = [
        SceneAction(action="show_title", text="LRU Cache"),
        SceneAction(action="show_hashmap", text="cache", values=[["key 1", "val A"], ["key 2", "val B"]], caption="Hash map for O(1) access"),
        SceneAction(action="show_graph", nodes=["MRU", "key2", "key1", "LRU"], caption="Doubly linked list for eviction order"),
        SceneAction(action="hashmap_insert", text="cache", label="get(1)", caption="Move accessed node to front (MRU)"),
        SceneAction(action="heap_pop", label="evict LRU", caption="Evict least recently used when capacity exceeded"),
    ]
    return AnimationPlan(
        algorithm="lru_cache",
        title="LRU Cache",
        data_structure="hash_map",
        scenes=scenes,
    )


def _plan_trie(ir: dict[str, Any]) -> AnimationPlan:
    scenes: list[SceneAction] = [
        SceneAction(action="show_title", text="Trie Visualization"),
        SceneAction(action="show_tree", tree={"value": "root", "left": {"value": "a"}, "right": {"value": "b"}}, caption="Prefix tree for strings"),
        SceneAction(action="show_caption", text="Insert and search prefixes character by character"),
    ]
    return AnimationPlan(
        algorithm="trie",
        title="Trie",
        data_structure="trie",
        scenes=scenes,
    )


def _plan_union_find(ir: dict[str, Any]) -> AnimationPlan:
    scenes: list[SceneAction] = [
        SceneAction(action="show_title", text="Union-Find (Disjoint Set)"),
        SceneAction(action="show_graph", nodes=["0", "1", "2", "3"], caption="Connected components"),
        SceneAction(action="visit_node", node="0", caption="find(0): locate root with path compression"),
        SceneAction(action="visit_node", node="1", caption="union(0,1): merge two sets"),
    ]
    return AnimationPlan(
        algorithm="union_find",
        title="Union-Find",
        data_structure="union_find",
        scenes=scenes,
    )


def _plan_dynamic_programming(ir: dict[str, Any]) -> AnimationPlan:
    scenes: list[SceneAction] = [
        SceneAction(action="show_title", text="Dynamic Programming"),
        SceneAction(action="create_array", values=[0, 1, 1, 2, 3, 5, 8], caption="DP table building bottom-up"),
        SceneAction(action="show_caption", text="Each cell depends on previously computed subproblems"),
    ]
    return AnimationPlan(
        algorithm="dynamic_programming",
        title="Dynamic Programming",
        data_structure="array",
        scenes=scenes,
    )


def _plan_stack_demo(ir: dict[str, Any]) -> AnimationPlan:
    return _plan_recursion(ir)


def _plan_dsa_overview(ir: dict[str, Any]) -> AnimationPlan:
    """Rich fallback for any parsed DSA code."""
    if ir.get("classes") or ir.get("methods"):
        return _plan_class_design(ir)
    return _plan_generic(ir)


def _plan_array(ir: dict[str, Any]) -> AnimationPlan:
    values = _extract_array_values(ir)
    scenes: list[SceneAction] = [
        SceneAction(action="show_title", text="Array Visualization"),
        SceneAction(action="create_array", values=values),
    ]

    loops = ir.get("loops") or []
    subscripts = ir.get("subscript_accesses") or []
    max_index = len(values) - 1

    if loops:
        for index in range(len(values)):
            scenes.append(
                SceneAction(
                    action="highlight_index",
                    index=index,
                    label=f"i = {index}",
                    caption=f"Access arr[{index}] = {values[index]}",
                )
            )
    elif subscripts:
        seen: set[int] = set()
        for access in subscripts:
            index = _parse_index(access.get("index", ""), len(values))
            if index is None or index in seen:
                continue
            seen.add(index)
            scenes.append(
                SceneAction(
                    action="highlight_index",
                    index=index,
                    label=f"i = {index}",
                    caption=f"Access arr[{index}] = {values[index]}",
                )
            )
    else:
        for index, value in enumerate(values):
            scenes.append(
                SceneAction(
                    action="highlight_index",
                    index=index,
                    label=f"index {index}",
                    caption=f"Element arr[{index}] = {value}",
                )
            )

    scenes.append(SceneAction(action="show_caption", text="Array traversal complete"))
    return AnimationPlan(
        algorithm=ir.get("algorithm") or "array_processing",
        title="Array Visualization",
        data_structure="array",
        description="Step-by-step array element access",
        scenes=scenes,
    )


def _plan_inorder(ir: dict[str, Any]) -> AnimationPlan:
    tree = DEFAULT_TREE
    path = [
        (10, "Visit root"),
        (5, "Move to left child"),
        (3, "Visit leftmost node"),
        (5, "Return to 5"),
        (7, "Visit right child of 5"),
        (10, "Return to root"),
        (20, "Visit right subtree"),
    ]
    return _plan_tree_traversal(ir, "Inorder Traversal", tree, path, "inorder_traversal")


def _plan_preorder(ir: dict[str, Any]) -> AnimationPlan:
    tree = DEFAULT_TREE
    path = [
        (10, "Visit root first"),
        (5, "Move to left child"),
        (3, "Visit left subtree"),
        (7, "Visit right child of 5"),
        (20, "Visit right subtree"),
    ]
    return _plan_tree_traversal(ir, "Preorder Traversal", tree, path, "preorder_traversal")


def _plan_postorder(ir: dict[str, Any]) -> AnimationPlan:
    tree = DEFAULT_TREE
    path = [
        (3, "Visit leftmost node"),
        (7, "Visit right child of 5"),
        (5, "Visit root of left subtree"),
        (20, "Visit right subtree"),
        (10, "Visit root last"),
    ]
    return _plan_tree_traversal(ir, "Postorder Traversal", tree, path, "postorder_traversal")


def _plan_tree_traversal(
    ir: dict[str, Any],
    title: str,
    tree: dict[str, Any],
    path: list[tuple[int, str]],
    algorithm: str,
) -> AnimationPlan:
    scenes: list[SceneAction] = [
        SceneAction(action="show_title", text=title),
        SceneAction(action="show_tree", tree=tree),
    ]

    previous: int | None = None
    for node, caption in path:
        if previous is not None and previous != node:
            scenes.append(
                SceneAction(action="move_pointer", **{"from": previous, "to": node, "caption": caption})
            )
        scenes.append(
            SceneAction(action="highlight_node", node=node, caption=caption)
        )
        scenes.append(SceneAction(action="visit_node", node=node, caption=f"Visited {node}"))
        previous = node

    scenes.append(SceneAction(action="show_caption", text=f"{title} complete"))
    return AnimationPlan(
        algorithm=algorithm,
        title=title,
        data_structure="binary_tree",
        description="Binary tree traversal with recursive calls",
        scenes=scenes,
    )


def _plan_tree_generic(ir: dict[str, Any]) -> AnimationPlan:
    return _plan_inorder(ir)


def _plan_binary_search(ir: dict[str, Any]) -> AnimationPlan:
    values = _extract_array_values(ir) or DEFAULT_SEARCH_ARRAY
    target = 23
    low, high = 0, len(values) - 1
    scenes: list[SceneAction] = [
        SceneAction(action="show_title", text="Binary Search"),
        SceneAction(action="create_array", values=values),
        SceneAction(action="show_caption", text=f"Searching for target = {target}"),
    ]

    while low <= high:
        mid = (low + high) // 2
        scenes.append(
            SceneAction(
                action="show_variables",
                variables={"low": low, "high": high, "mid": mid},
                caption=f"low={low}, high={high}, mid={mid}",
            )
        )
        scenes.append(
            SceneAction(
                action="highlight_range",
                index=mid,
                label=f"mid = {mid}",
                caption=f"Compare arr[{mid}] = {values[mid]} with target {target}",
            )
        )
        if values[mid] == target:
            scenes.append(
                SceneAction(
                    action="highlight_index",
                    index=mid,
                    label="found",
                    caption=f"Target found at index {mid}",
                )
            )
            break
        if values[mid] < target:
            low = mid + 1
            scenes.append(
                SceneAction(action="show_caption", text="Target is in the right half")
            )
        else:
            high = mid - 1
            scenes.append(
                SceneAction(action="show_caption", text="Target is in the left half")
            )
    else:
        scenes.append(SceneAction(action="show_caption", text="Target not found"))

    return AnimationPlan(
        algorithm="binary_search",
        title="Binary Search",
        data_structure="array",
        description="Binary search on a sorted array",
        scenes=scenes,
    )


def _plan_bubble_sort(ir: dict[str, Any]) -> AnimationPlan:
    values = _extract_array_values(ir) or list(DEFAULT_SORT_ARRAY)
    scenes: list[SceneAction] = [
        SceneAction(action="show_title", text="Bubble Sort"),
        SceneAction(action="create_array", values=values),
    ]

    arr = [int(v) for v in values]
    n = len(arr)
    for i in range(n):
        for j in range(0, n - i - 1):
            scenes.append(
                SceneAction(
                    action="compare_indices",
                    index=j,
                    label=str(j + 1),
                    caption=f"Compare arr[{j}]={arr[j]} and arr[{j + 1}]={arr[j + 1]}",
                )
            )
            if arr[j] > arr[j + 1]:
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
                scenes.append(
                    SceneAction(
                        action="swap_indices",
                        index=j,
                        label=str(j + 1),
                        values=list(arr),
                        caption=f"Swap → {arr}",
                    )
                )

    scenes.append(
        SceneAction(action="create_array", values=arr, caption="Sorted array")
    )
    scenes.append(SceneAction(action="show_caption", text="Bubble sort complete"))
    return AnimationPlan(
        algorithm="bubble_sort",
        title="Bubble Sort",
        data_structure="array",
        description="Adjacent element comparison and swapping",
        scenes=scenes,
    )


def _plan_selection_sort(ir: dict[str, Any]) -> AnimationPlan:
    values = _extract_array_values(ir) or list(DEFAULT_SORT_ARRAY)
    arr = [int(v) for v in values]
    scenes: list[SceneAction] = [
        SceneAction(action="show_title", text="Selection Sort"),
        SceneAction(action="create_array", values=arr),
    ]

    n = len(arr)
    for i in range(n):
        min_idx = i
        for j in range(i + 1, n):
            scenes.append(
                SceneAction(
                    action="compare_indices",
                    index=j,
                    label=str(min_idx),
                    caption=f"Find minimum from index {i}",
                )
            )
            if arr[j] < arr[min_idx]:
                min_idx = j
        if min_idx != i:
            arr[i], arr[min_idx] = arr[min_idx], arr[i]
            scenes.append(
                SceneAction(
                    action="swap_indices",
                    index=i,
                    label=str(min_idx),
                    values=list(arr),
                    caption=f"Place minimum at index {i}",
                )
            )

    scenes.append(SceneAction(action="show_caption", text="Selection sort complete"))
    return AnimationPlan(
        algorithm="selection_sort",
        title="Selection Sort",
        data_structure="array",
        scenes=scenes,
    )


def _plan_insertion_sort(ir: dict[str, Any]) -> AnimationPlan:
    values = _extract_array_values(ir) or list(DEFAULT_SORT_ARRAY)
    arr = [int(v) for v in values]
    scenes: list[SceneAction] = [
        SceneAction(action="show_title", text="Insertion Sort"),
        SceneAction(action="create_array", values=arr),
    ]

    for i in range(1, len(arr)):
        key = arr[i]
        scenes.append(
            SceneAction(
                action="highlight_index",
                index=i,
                label=f"key = {key}",
                caption=f"Insert key {key} into sorted portion",
            )
        )
        j = i - 1
        while j >= 0 and arr[j] > key:
            arr[j + 1] = arr[j]
            j -= 1
            scenes.append(
                SceneAction(
                    action="create_array",
                    values=list(arr),
                    caption="Shift larger elements right",
                )
            )
        arr[j + 1] = key
        scenes.append(
            SceneAction(action="create_array", values=list(arr), caption=f"Insert {key}")
        )

    scenes.append(SceneAction(action="show_caption", text="Insertion sort complete"))
    return AnimationPlan(
        algorithm="insertion_sort",
        title="Insertion Sort",
        data_structure="array",
        scenes=scenes,
    )


def _plan_recursion(ir: dict[str, Any]) -> AnimationPlan:
    fn = next((f for f in ir.get("functions", []) if f.get("recursive")), None)
    fn_name = fn["name"] if fn else "recursive_function"
    depth = 4
    scenes: list[SceneAction] = [
        SceneAction(action="show_title", text="Recursion Stack"),
        SceneAction(action="show_caption", text=f"Tracing calls to {fn_name}()"),
    ]

    for level in range(depth, 0, -1):
        scenes.append(
            SceneAction(
                action="push_stack",
                label=f"{fn_name}({level})",
                caption=f"Call {fn_name}({level})",
            )
        )
    scenes.append(
        SceneAction(action="show_caption", text="Base case reached — returning")
    )
    for level in range(1, depth + 1):
        scenes.append(
            SceneAction(
                action="pop_stack",
                label=f"{fn_name}({level})",
                caption=f"Return from {fn_name}({level})",
            )
        )

    return AnimationPlan(
        algorithm="recursion",
        title="Recursion Visualization",
        data_structure="stack",
        description="Call stack growth and unwinding",
        scenes=scenes,
    )


def _plan_graph_traversal(ir: dict[str, Any], kind: str) -> AnimationPlan:
    nodes = ["A", "B", "C", "D"]
    order = ["A", "B", "D", "C"] if kind == "BFS" else ["A", "B", "C", "D"]
    scenes: list[SceneAction] = [
        SceneAction(action="show_title", text=f"Graph {kind}"),
        SceneAction(action="show_graph", nodes=nodes),
    ]
    for node in order:
        scenes.append(
            SceneAction(action="visit_node", node=node, caption=f"Visit node {node}")
        )
    scenes.append(SceneAction(action="show_caption", text=f"{kind} complete"))
    return AnimationPlan(
        algorithm=kind.lower(),
        title=f"Graph {kind}",
        data_structure="graph",
        scenes=scenes,
    )


def _plan_graph_generic(ir: dict[str, Any]) -> AnimationPlan:
    return _plan_graph_traversal(ir, "BFS")


def _plan_generic(ir: dict[str, Any]) -> AnimationPlan:
    algorithm = ir.get("algorithm") or "code_analysis"
    operations = ir.get("operations") or []
    scenes: list[SceneAction] = [
        SceneAction(action="show_title", text="Code Visualization"),
        SceneAction(
            action="show_caption",
            text=f"Language: {ir.get('language', 'unknown')} | Algorithm: {algorithm}",
        ),
    ]

    for op in operations[:8]:
        scenes.append(SceneAction(action="show_caption", text=op))

    if not operations:
        scenes.append(
            SceneAction(
                action="show_caption",
                text="Parser extracted structure — add more code for richer visuals",
            )
        )

    return AnimationPlan(
        algorithm=algorithm,
        title="Code Visualization",
        data_structure=(ir.get("data_structures") or [None])[0],
        description="Generic code structure overview",
        scenes=scenes,
    )


def _extract_array_values(ir: dict[str, Any]) -> list[int | float | str]:
    for array in ir.get("arrays") or []:
        init = array.get("initializer")
        if isinstance(init, list) and init:
            return init
    return [5, 2, 8, 1]


def _parse_index(index_text: str, length: int) -> int | None:
    index_text = str(index_text).strip()
    if index_text.isdigit():
        value = int(index_text)
        return value if 0 <= value < length else None
    return None
