#include <iostream>
#include <vector>
using namespace std;

int main() {
    vector<int> v = {1, 2, 3, 4, 5};
    int l = 0, r = v.size() - 1;
    while (l < r) {
        swap(v[l], v[r]);
        l++;
        r--;
    }
    for (int x : v) cout << x << " ";
}
