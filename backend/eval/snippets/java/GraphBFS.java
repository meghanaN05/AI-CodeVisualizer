import java.util.*;

public class GraphBFS {
    static void addEdge(List<List<Integer>> adj, int u, int v) {
        adj.get(u).add(v);
        adj.get(v).add(u);
    }

    public static void main(String[] args) {
        int n = 4;
        List<List<Integer>> adj = new ArrayList<>();
        for (int i = 0; i < n; i++) adj.add(new ArrayList<>());
        addEdge(adj, 0, 1);
        addEdge(adj, 0, 2);
        addEdge(adj, 1, 3);
        addEdge(adj, 2, 3);

        boolean[] visited = new boolean[n];
        Queue<Integer> q = new LinkedList<>();
        q.add(0);
        visited[0] = true;
        while (!q.isEmpty()) {
            int u = q.poll();
            System.out.println(u);
            for (int v : adj.get(u)) {
                if (!visited[v]) {
                    visited[v] = true;
                    q.add(v);
                }
            }
        }
    }
}
