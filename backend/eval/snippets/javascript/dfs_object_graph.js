const graph = { 1: [2, 3], 2: [4], 3: [4], 4: [] };

function dfs(node, visited = new Set()) {
  visited.add(node);
  console.log(node);
  for (const next of graph[node]) {
    if (!visited.has(next)) dfs(next, visited);
  }
  return visited;
}

dfs(1);
