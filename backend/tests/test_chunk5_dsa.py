"""
test_chunk5_dsa.py — Complex DSA execution testing for Chunk 5

Validates that complex algorithms commonly found in the final difficult rounds 
(like DP, Graph Algorithms, and efficient O(N log N) structures) run correctly, 
and that inefficient algorithms TLE correctly.
"""

import pytest
import pytest_asyncio
from backend.runner.python_runner import run_python
from backend.runner.cpp_runner import run_cpp
from backend.runner.base_runner import RunStatus

# ═══════════════════════════════════════════════════════════════════════════════
#  TEST 1: Python — Longest Increasing Subsequence (O(N log N))
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_python_dsa_lis():
    """Test Python O(N log N) Longest Increasing Subsequence logic."""
    code = """
from bisect import bisect_left

def lis():
    input_data = []
    while True:
        try:
            input_data.extend(input().split())
        except EOFError:
            break
    if not input_data:
        return
    n = int(input_data[0])
    arr = [int(x) for x in input_data[1:]]
    
    sub = []
    for x in arr:
        pos = bisect_left(sub, x)
        if pos == len(sub):
            sub.append(x)
        else:
            sub[pos] = x
            
    print(len(sub))

if __name__ == '__main__':
    lis()
"""
    # 10 elements: LIS should be [10, 22, 33, 50, 60, 80] = length 6
    stdin_data = "10\n10 22 9 33 21 50 41 60 80 1"
    
    result = await run_python(code, stdin_data=stdin_data)
    
    assert result.status == RunStatus.SUCCESS, f"Failed: {result.error_message}"
    assert result.stdout.strip() == "6"


# ═══════════════════════════════════════════════════════════════════════════════
#  TEST 2: C++ — Dijkstra's Algorithm (O((V+E) log V))
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cpp_dsa_dijkstra():
    """Test C++ Dijkstra algorithm using priority_queue."""
    import shutil
    if not shutil.which("g++"):
        pytest.skip("g++ not found")

    code = """
#include <iostream>
#include <vector>
#include <queue>
#include <limits>

using namespace std;

const int INF = numeric_limits<int>::max();

int main() {
    ios_base::sync_with_stdio(false);
    cin.tie(NULL);

    int V, E, S;
    if (!(cin >> V >> E >> S)) return 0;

    vector<vector<pair<int, int>>> adj(V);
    for (int i = 0; i < E; ++i) {
        int u, v, w;
        cin >> u >> v >> w;
        adj[u].push_back({v, w});
        adj[v].push_back({u, w}); // Undirected
    }

    vector<int> dist(V, INF);
    dist[S] = 0;
    priority_queue<pair<int, int>, vector<pair<int, int>>, greater<>> pq;
    pq.push({0, S});

    while (!pq.empty()) {
        int d = pq.top().first;
        int u = pq.top().second;
        pq.pop();

        if (d > dist[u]) continue;

        for (auto& edge : adj[u]) {
            int v = edge.first;
            int weight = edge.second;

            if (dist[u] + weight < dist[v]) {
                dist[v] = dist[u] + weight;
                pq.push({dist[v], v});
            }
        }
    }

    for (int i = 0; i < V; ++i) {
        if (dist[i] == INF) cout << "-1 ";
        else cout << dist[i] << " ";
    }
    cout << "\\n";

    return 0;
}
"""
    # Graph: 5 Vertices, 6 Edges, Source = 0
    # Edges: 0-1 (2), 0-3 (1), 1-2 (3), 1-3 (2), 1-4 (1), 3-4 (4), 2-4 (5)
    # Expected Distances from 0: 0, 2, 5, 1, 3
    stdin_data = """5 7 0
0 1 2
0 3 1
1 2 3
1 3 2
1 4 1
3 4 4
2 4 5
"""
    
    result = await run_cpp(code, stdin_data=stdin_data)
    
    assert result.status == RunStatus.SUCCESS, f"Failed: {result.error_message}"
    assert result.stdout.strip() == "0 2 5 1 3"


# ═══════════════════════════════════════════════════════════════════════════════
#  TEST 3: Time Limit Exceeded (TLE) — O(N^2) on large N
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_python_dsa_tle_inefficient():
    """Verify that an intentionally slow algorithm (O(N^2)) gets forcefully terminated (TIMEOUT)."""
    # Inefficient two-sum on 50,000 elements which will take > 2 seconds easily in Python
    code = """
def solve():
    n = 50000
    arr = list(range(n))
    target = 99999999
    
    # O(N^2) algorithm
    for i in range(len(arr)):
        for j in range(i+1, len(arr)):
            if arr[i] + arr[j] == target:
                print("Found")
                return

solve()
"""
    # Force 1.0s timeout
    result = await run_python(code, timeout=1.0)
    
    assert result.status == RunStatus.TIMEOUT
    assert result.time_taken >= 0.9


# ═══════════════════════════════════════════════════════════════════════════════
#  TEST 4: C++ — Extremely large memory allocation (Safety handling)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cpp_dsa_memory_limit_crash():
    """Verify that C++ programs failing from bad allocations handle the error cleanly."""
    import shutil
    if not shutil.which("g++"):
        pytest.skip("g++ not found")

    # Tries to allocate astronomical memory on heap
    code = """
#include <iostream>
#include <vector>
using namespace std;

int main() {
    // Attempt to allocate continuous 100 GB memory space
    try {
        vector<long long> massive_vec(10000000000ULL, 1); 
        cout << massive_vec[0] << endl;
    } catch (...) {
        return 1; // Catch bad_alloc and return non-zero
    }
    return 0;
}
"""
    result = await run_cpp(code)
    
    # OS will either throw bad_alloc or terminate the process.
    # We should get a RUNTIME_ERROR, not crash the backend.
    assert result.status == RunStatus.RUNTIME_ERROR
