from collections import deque

graph = {"S": ["X", "Y"], "X": ["Z"], "Y": ["Z"], "Z": []}


def bfs(start):
    visited = {start}
    order = []
    q = deque([start])
    while q:
        node = q.popleft()
        order.append(node)
        for nxt in graph[node]:
            if nxt not in visited:
                visited.add(nxt)
                q.append(nxt)
    return order


print(bfs("S"))
