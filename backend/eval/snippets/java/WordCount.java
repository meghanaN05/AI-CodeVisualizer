import java.util.*;

public class WordCount {
    public static void main(String[] args) {
        String[] words = {"apple", "pear", "apple", "fig"};
        Map<String, Integer> counts = new HashMap<>();
        for (String w : words) {
            counts.put(w, counts.getOrDefault(w, 0) + 1);
        }
        System.out.println(counts);
    }
}
