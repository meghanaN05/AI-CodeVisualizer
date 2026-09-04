export const LANGUAGES = [
  { id: "cpp", label: "C++", accent: "#00599C" },
  { id: "python", label: "Python", accent: "#3776AB" },
  { id: "java", label: "Java", accent: "#EA6D24" },
  { id: "javascript", label: "JavaScript", accent: "#F0DB4F" },
];

export const SAMPLE_CODE = {
  cpp: `#include <iostream>
using namespace std;

int main() {
    int arr[] = {5, 2, 8, 1};

    for(int i = 0; i < 4; i++) {
        cout << arr[i] << " ";
    }

    return 0;
}`,
  python: `def bubble_sort(arr):
    n = len(arr)
    for i in range(n):
        for j in range(0, n - i - 1):
            if arr[j] > arr[j + 1]:
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
    return arr

print(bubble_sort([5, 2, 8, 1]))`,
  java: `public class Main {
    public static void main(String[] args) {
        int[] arr = {5, 2, 8, 1};

        for (int i = 0; i < arr.length; i++) {
            System.out.print(arr[i] + " ");
        }
    }
}`,
  javascript: `function bubbleSort(arr) {
  for (let i = 0; i < arr.length; i++) {
    for (let j = 0; j < arr.length - i - 1; j++) {
      if (arr[j] > arr[j + 1]) {
        [arr[j], arr[j + 1]] = [arr[j + 1], arr[j]];
      }
    }
  }
  return arr;
}

console.log(bubbleSort([5, 2, 8, 1]));`,
};
