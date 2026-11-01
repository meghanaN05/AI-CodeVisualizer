import java.util.*;

public class TopK {
    public static void main(String[] args) {
        int[] nums = {5, 1, 8, 3, 9, 2};
        PriorityQueue<Integer> pq = new PriorityQueue<>();
        for (int x : nums) {
            pq.offer(x);
            if (pq.size() > 3) pq.poll();
        }
        System.out.println(pq);
    }
}
