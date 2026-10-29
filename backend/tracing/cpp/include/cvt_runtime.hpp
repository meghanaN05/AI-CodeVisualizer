// Execution-trace runtime for instrumented C++ snippets.
//
// The instrumenter (tracing/cpp/instrument.py) rewrites a snippet so that
//   * every function body opens with a cvt_rt::Frame guard (call stack),
//   * every declared variable is followed by a cvt_rt::Var / Arr guard that
//     registers its name and address while it is in scope,
//   * every statement is preceded by cvt_rt::step(LINE), and returns go
//     through cvt_rt::ret / retv so the returned value is recorded.
// Each step serializes all registered variables into the language-neutral
// trace format (see tracing/__init__.py) and writes one JSON line, prefixed
// with '\x1e', to the process's ORIGINAL stdout. The program's own stdout
// (cout, printf, ...) is redirected to a temp file and reported per step.
//
// Only standard C++17 plus POSIX is used, so it works with libc++ and
// libstdc++. Heap blocks are tracked by replacing global operator new/delete
// so pointers are only dereferenced when they point at live memory.
#pragma once

#include <algorithm>
#include <array>
#include <bitset>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <exception>
#include <forward_list>
#include <functional>
#include <iostream>
#include <list>
#include <map>
#include <new>
#include <optional>
#include <queue>
#include <set>
#include <stack>
#include <string>
#include <string_view>
#include <tuple>
#include <type_traits>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>


#ifndef CVT_MAX_STEPS
#define CVT_MAX_STEPS 1500
#endif

namespace cvt_rt {

constexpr std::size_t MAX_ITEMS = 64;
constexpr std::size_t MAX_STR = 1000;
constexpr std::size_t MAX_HEAP = 500;
constexpr std::size_t MAX_STDOUT_DELTA = 4000;
constexpr std::size_t MAX_TRACE_BYTES = 15u << 20;

enum : unsigned { OWN = 1, HIDDEN = 2, GLOBAL = 4 };

// ------------------------------------------------------------ bookkeeping

// Allocator for the runtime's own tables so they never recurse into the
// replaced operator new.
template <class T>
struct MAlloc {
  using value_type = T;
  MAlloc() noexcept {}
  template <class U>
  MAlloc(const MAlloc<U>&) noexcept {}
  T* allocate(std::size_t n) {
    void* p = std::malloc(n * sizeof(T));
    if (!p) throw std::bad_alloc();
    return static_cast<T*>(p);
  }
  void deallocate(T* p, std::size_t) noexcept { std::free(p); }
  template <class U>
  bool operator==(const MAlloc<U>&) const noexcept { return true; }
  template <class U>
  bool operator!=(const MAlloc<U>&) const noexcept { return false; }
};

struct W;
using ObjFn = void (*)(W&, const void*, std::size_t, std::size_t);

struct Block {
  std::size_t size;
};
struct ArrEntry {
  std::size_t elem_size, n, aux;
  int type;
  ObjFn fn;
};
struct VarRec {
  const char* name;
  const void* addr;
  std::size_t size, n, aux;
  ObjFn write;  // writes the VALUE (scalar inline or a ref)
  unsigned flags;
  long frame;
};
struct FrameRec {
  const char* name;
  int line;
  bool is_main;
};

template <class K, class V>
using MMap = std::map<K, V, std::less<K>, MAlloc<std::pair<const K, V>>>;
using IdKey = std::pair<std::uintptr_t, int>;

struct State {
  MMap<std::uintptr_t, Block> blocks;
  MMap<IdKey, long> ids;
  MMap<std::uintptr_t, ArrEntry> arrays;
  std::vector<VarRec, MAlloc<VarRec>> vars, globals;
  std::vector<FrameRec, MAlloc<FrameRec>> frames;
  long next_id = 0;
  int steps = 0;
  bool inside = false;
  bool done = false;
  bool truncated = false;
  int trace_fd = -1;
  int out_fd = -1;
  long long printed = 0;
  bool initialized = false;
  std::size_t bytes = 0;
};

inline State& S() {
  static State* s = new (std::malloc(sizeof(State))) State();
  return *s;
}

inline int next_type() {
  static int counter = 0;
  return ++counter;
}
template <class T>
int type_no() {
  static const int id = next_type();
  return id;
}
template <class T>
struct ArrOf {};
template <class T>
struct Arr2Of {};

inline void forget_ids(std::uintptr_t lo, std::uintptr_t hi) {
  auto& ids = S().ids;
  auto a = ids.lower_bound(IdKey(lo, INT32_MIN));
  auto b = ids.lower_bound(IdKey(hi, INT32_MIN));
  ids.erase(a, b);
}

inline void on_alloc(void* p, std::size_t n) {
  State& s = S();
  if (!p || s.inside) return;
  s.blocks[reinterpret_cast<std::uintptr_t>(p)] = Block{n ? n : 1};
}

inline void on_free(void* p) {
  if (!p) return;
  State& s = S();
  auto it = s.blocks.find(reinterpret_cast<std::uintptr_t>(p));
  if (it == s.blocks.end()) return;
  std::uintptr_t lo = it->first, hi = it->first + it->second.size;
  s.blocks.erase(it);
  forget_ids(lo, hi);
}

inline void* c_malloc(std::size_t n) {
  void* p = std::malloc(n);
  on_alloc(p, n);
  return p;
}
inline void* c_calloc(std::size_t n, std::size_t size) {
  void* p = std::calloc(n, size);
  on_alloc(p, n * size);
  return p;
}
inline void* c_realloc(void* old, std::size_t n) {
  on_free(old);
  void* p = std::realloc(old, n);
  on_alloc(p, n);
  return p;
}
inline void c_free(void* p) {
  on_free(p);
  std::free(p);
}

// Is [a, a + size) inside memory the program currently owns?
inline bool valid(std::uintptr_t a, std::size_t size) {
  State& s = S();
  auto in = [&](const VarRec& v) {
    auto lo = reinterpret_cast<std::uintptr_t>(v.addr);
    return a >= lo && a + size <= lo + v.size;
  };
  for (const auto& v : s.vars)
    if (in(v)) return true;
  for (const auto& v : s.globals)
    if (in(v)) return true;
  auto it = s.blocks.upper_bound(a);
  if (it != s.blocks.begin()) {
    --it;
    if (a + size <= it->first + it->second.size) return true;
  }
  return false;
}

// ------------------------------------------------------------- the writer

struct Pending {
  const void* addr;
  ObjFn fn;
  std::size_t n, aux;
  long id;
};

inline void json_str(std::string& out, const char* s, std::size_t n) {
  static const char* hex = "0123456789abcdef";
  out += '"';
  for (std::size_t i = 0; i < n; ++i) {
    unsigned char c = static_cast<unsigned char>(s[i]);
    switch (c) {
      case '"': out += "\\\""; break;
      case '\\': out += "\\\\"; break;
      case '\n': out += "\\n"; break;
      case '\r': out += "\\r"; break;
      case '\t': out += "\\t"; break;
      default:
        if (c < 0x20 || c == 0x7f) {
          out += "\\u00";
          out += hex[c >> 4];
          out += hex[c & 15];
        } else {
          out += static_cast<char>(c);
        }
    }
  }
  out += '"';
}

struct W {
  std::string* buf = nullptr;
  std::vector<Pending> queue;
  std::unordered_set<long> emitted;
  bool first = true;  // comma state for object fields

  void raw(const char* s) { *buf += s; }
  void str(const char* s, std::size_t n) { json_str(*buf, s, n < MAX_STR ? n : MAX_STR); }
  void null() { *buf += "null"; }
  void unknown() { *buf += "\"?\""; }

  void ref(const void* addr, int type, ObjFn fn, std::size_t n = 0, std::size_t aux = 0) {
    State& s = S();
    IdKey key(reinterpret_cast<std::uintptr_t>(addr), type);
    auto it = s.ids.find(key);
    long id;
    if (it == s.ids.end()) {
      id = ++s.next_id;
      s.ids.emplace(key, id);
    } else {
      id = it->second;
    }
    if (!emitted.count(id)) {
      if (emitted.size() >= MAX_HEAP) {
        *buf += "\"…\"";
        return;
      }
      emitted.insert(id);
      queue.push_back(Pending{addr, fn, n, aux, id});
    }
    *buf += "{\"ref\":\"";
    *buf += std::to_string(id);
    *buf += "\"}";
  }

  template <class X>
  void value(const X& x);
  template <class X>
  void field(const char* name, const X& x);
  template <class It>
  void seq(const char* kind, It begin, It end);

  void obj_begin(const char* cls) {
    *buf += "{\"kind\":\"object\",\"class\":";
    json_str(*buf, cls, std::strlen(cls));
    *buf += ",\"fields\":{";
    first = true;
  }
  void obj_end() { *buf += "}}"; }
};

// ------------------------------------------------------------ serializers

template <class T, class = void>
struct Ser {
  static constexpr bool known = false;
  static constexpr bool heap = false;
  static void write(W& w, const T&) { w.unknown(); }
};

template <class T>
using Plain = std::remove_cv_t<T>;

template <class T>
constexpr bool is_char_v = std::is_same<Plain<T>, char>::value;

template <class T, class = void>
struct is_complete : std::false_type {};
template <class T>
struct is_complete<T, std::void_t<decltype(sizeof(T))>> : std::true_type {};

template <>
struct Ser<bool> {
  static constexpr bool known = true, heap = false;
  static void write(W& w, bool v) { w.raw(v ? "true" : "false"); }
};

template <>
struct Ser<char> {
  static constexpr bool known = true, heap = false;
  static void write(W& w, char v) { w.str(&v, 1); }
};

template <class T>
struct Ser<T, std::enable_if_t<std::is_integral<T>::value && !std::is_same<T, bool>::value &&
                               !std::is_same<T, char>::value>> {
  static constexpr bool known = true, heap = false;
  static void write(W& w, T v) { *w.buf += std::to_string(v); }
};

template <class T>
struct Ser<T, std::enable_if_t<std::is_floating_point<T>::value>> {
  static constexpr bool known = true, heap = false;
  static void write(W& w, T v) {
    long double x = v;
    if (std::isnan(x)) return w.raw("\"NaN\"");
    if (std::isinf(x)) return w.raw(x > 0 ? "\"∞\"" : "\"-∞\"");
    char tmp[64];
    double d = static_cast<double>(v);
    std::snprintf(tmp, sizeof tmp, "%.15g", d);
    if (std::strtod(tmp, nullptr) != d) std::snprintf(tmp, sizeof tmp, "%.17g", d);
    *w.buf += tmp;
  }
};

template <class T>
struct Ser<T, std::enable_if_t<std::is_enum<T>::value>> {
  static constexpr bool known = true, heap = false;
  static void write(W& w, T v) { *w.buf += std::to_string(static_cast<long long>(v)); }
};

template <>
struct Ser<std::nullptr_t> {
  static constexpr bool known = true, heap = false;
  static void write(W& w, std::nullptr_t) { w.null(); }
};

template <class Tr, class A>
struct Ser<std::basic_string<char, Tr, A>> {
  static constexpr bool known = true, heap = false;
  static void write(W& w, const std::basic_string<char, Tr, A>& v) { w.str(v.data(), v.size()); }
};

template <>
struct Ser<std::string_view> {
  static constexpr bool known = true, heap = false;
  static void write(W& w, std::string_view v) { w.str(v.data(), v.size()); }
};

template <class T>
struct Ser<std::optional<T>> {
  static constexpr bool known = Ser<Plain<T>>::known, heap = false;
  static void write(W& w, const std::optional<T>& v) {
    if (v) w.value(*v);
    else w.null();
  }
};

template <std::size_t N>
struct Ser<std::bitset<N>> {
  static constexpr bool known = true, heap = false;
  static void write(W& w, const std::bitset<N>& v) {
    std::string s = v.to_string();
    w.str(s.data(), s.size());
  }
};

// Containers, tuples and user objects live on the heap: the value is a ref
// and the object is written once per step under its id.
template <class T>
struct HeapSer {
  static constexpr bool known = true, heap = true;
  static void write(W& w, const T& v) { w.ref(std::addressof(v), type_no<T>(), &thunk); }
  static void thunk(W& w, const void* p, std::size_t, std::size_t) {
    Ser<T>::obj(w, *static_cast<const T*>(p));
  }
};

#define CVT_SEQ(TEMPLATE_HEAD, TYPE, KIND)                      \
  TEMPLATE_HEAD struct Ser<TYPE> : HeapSer<TYPE> {              \
    static void obj(W& w, const TYPE& v) {                      \
      w.seq(KIND, v.begin(), v.end());                          \
    }                                                           \
  };
#define CVT_COMMA ,
CVT_SEQ(template <class T CVT_COMMA class A>, std::vector<T CVT_COMMA A>, "list")
CVT_SEQ(template <class T CVT_COMMA class A>, std::deque<T CVT_COMMA A>, "list")
CVT_SEQ(template <class T CVT_COMMA class A>, std::list<T CVT_COMMA A>, "list")
CVT_SEQ(template <class T CVT_COMMA class A>, std::forward_list<T CVT_COMMA A>, "list")
CVT_SEQ(template <class T CVT_COMMA std::size_t N>, std::array<T CVT_COMMA N>, "list")
CVT_SEQ(template <class T CVT_COMMA class C CVT_COMMA class A>, std::set<T CVT_COMMA C CVT_COMMA A>, "set")
CVT_SEQ(template <class T CVT_COMMA class C CVT_COMMA class A>, std::multiset<T CVT_COMMA C CVT_COMMA A>, "set")
CVT_SEQ(template <class T CVT_COMMA class H CVT_COMMA class E CVT_COMMA class A>,
        std::unordered_set<T CVT_COMMA H CVT_COMMA E CVT_COMMA A>, "set")
CVT_SEQ(template <class T CVT_COMMA class H CVT_COMMA class E CVT_COMMA class A>,
        std::unordered_multiset<T CVT_COMMA H CVT_COMMA E CVT_COMMA A>, "set")
#undef CVT_SEQ

template <class A>
struct Ser<std::vector<bool, A>> : HeapSer<std::vector<bool, A>> {
  static void obj(W& w, const std::vector<bool, A>& v) {
    w.raw("{\"kind\":\"list\",\"items\":[");
    std::size_t i = 0;
    for (bool b : v) {
      if (i == MAX_ITEMS) break;
      if (i++) w.raw(",");
      w.raw(b ? "true" : "false");
    }
    w.raw("]}");
  }
};

template <class M>
struct MapSer : HeapSer<M> {
  static void obj(W& w, const M& m) {
    w.raw("{\"kind\":\"dict\",\"entries\":[");
    std::size_t i = 0;
    for (const auto& kv : m) {
      if (i == MAX_ITEMS) break;
      if (i++) w.raw(",");
      w.raw("[");
      w.value(kv.first);
      w.raw(",");
      w.value(kv.second);
      w.raw("]");
    }
    w.raw("]}");
  }
};
template <class K, class V, class C, class A>
struct Ser<std::map<K, V, C, A>> : MapSer<std::map<K, V, C, A>> {};
template <class K, class V, class C, class A>
struct Ser<std::multimap<K, V, C, A>> : MapSer<std::multimap<K, V, C, A>> {};
template <class K, class V, class H, class E, class A>
struct Ser<std::unordered_map<K, V, H, E, A>> : MapSer<std::unordered_map<K, V, H, E, A>> {};
template <class K, class V, class H, class E, class A>
struct Ser<std::unordered_multimap<K, V, H, E, A>> : MapSer<std::unordered_multimap<K, V, H, E, A>> {};

template <class A, class B>
struct Ser<std::pair<A, B>> : HeapSer<std::pair<A, B>> {
  static void obj(W& w, const std::pair<A, B>& p) {
    w.raw("{\"kind\":\"tuple\",\"items\":[");
    w.value(p.first);
    w.raw(",");
    w.value(p.second);
    w.raw("]}");
  }
};

template <class... Ts>
struct Ser<std::tuple<Ts...>> : HeapSer<std::tuple<Ts...>> {
  static void obj(W& w, const std::tuple<Ts...>& t) {
    w.raw("{\"kind\":\"tuple\",\"items\":[");
    bool first = true;
    std::apply(
        [&](const auto&... xs) {
          ((w.raw(first ? "" : ","), first = false, w.value(xs)), ...);
        },
        t);
    w.raw("]}");
  }
};

// Container adaptors expose their storage as the protected member `c`
// (and priority_queue its comparator as `comp`); both are standard names.
template <class Ad>
struct AdaptorAccess : Ad {
  static const typename Ad::container_type& items(const Ad& a) { return a.*(&AdaptorAccess::c); }
};
template <class Ad>
struct PqAccess : Ad {
  static const typename Ad::container_type& items(const Ad& a) { return a.*(&PqAccess::c); }
  static auto comparator(const Ad& a) { return a.*(&PqAccess::comp); }
};

template <class T, class C>
struct Ser<std::stack<T, C>> : HeapSer<std::stack<T, C>> {  // bottom ... top
  static void obj(W& w, const std::stack<T, C>& s) {
    const auto& c = AdaptorAccess<std::stack<T, C>>::items(s);
    w.seq("list", c.begin(), c.end());
  }
};
template <class T, class C>
struct Ser<std::queue<T, C>> : HeapSer<std::queue<T, C>> {  // front ... back
  static void obj(W& w, const std::queue<T, C>& q) {
    const auto& c = AdaptorAccess<std::queue<T, C>>::items(q);
    w.seq("list", c.begin(), c.end());
  }
};
template <class T, class C, class Cmp>
struct Ser<std::priority_queue<T, C, Cmp>> : HeapSer<std::priority_queue<T, C, Cmp>> {
  // The underlying container in its real binary-heap layout (top at index
  // 0, children of i at 2i+1 and 2i+2), so the planner can draw the tree.
  static void obj(W& w, const std::priority_queue<T, C, Cmp>& q) {
    using PQ = std::priority_queue<T, C, Cmp>;
    const auto& c = PqAccess<PQ>::items(q);
    w.raw("{\"kind\":\"list\",\"items\":[");
    std::size_t i = 0;
    for (const auto& x : c) {
      if (i >= MAX_ITEMS) break;
      if (i++) w.raw(",");
      w.value(x);
    }
    w.raw("]}");
  }
};

// C arrays: one heap object per array, keyed by its first element's address
// and element type, so a pointer parameter (int arr[]) resolves to it.
template <class E>
void arr_thunk(W& w, const void* p, std::size_t n, std::size_t) {
  const E* a = static_cast<const E*>(p);
  if constexpr (is_char_v<E>) {
    std::size_t len = 0;
    while (len < n && a[len] != '\0') ++len;
    n = len;
  }
  w.seq("list", a, a + n);
}

template <class E>
void arr2_thunk(W& w, const void* p, std::size_t rows, std::size_t cols) {
  const E* a = static_cast<const E*>(p);
  w.raw("{\"kind\":\"list\",\"items\":[");
  for (std::size_t r = 0; r < rows && r < MAX_ITEMS; ++r) {
    if (r) w.raw(",");
    w.ref(a + r * cols, type_no<ArrOf<E>>(), &arr_thunk<E>, cols);
  }
  w.raw("]}");
}

template <class E, std::size_t N>
struct Ser<E[N]> {
  static constexpr bool known = true, heap = true;
  static void write(W& w, const E (&v)[N]) {
    w.ref(&v[0], type_no<ArrOf<Plain<E>>>(), &arr_thunk<Plain<E>>, N);
  }
};

template <class T>
struct Ser<T, std::void_t<decltype(&T::CVTser_)>> : HeapSer<T> {
  static void obj(W& w, const T& v) {
    w.obj_begin(T::CVTname_());
    v.CVTser_(w);
    w.obj_end();
  }
};

template <class U>
void write_pointee(W& w, const U* p) {
  if constexpr (Ser<U>::known) Ser<U>::write(w, *p);
  else w.unknown();
}

template <class T>
struct Ser<T*, std::enable_if_t<!std::is_function<T>::value && !std::is_void<T>::value &&
                                !is_char_v<T>>> {
  using U = Plain<T>;
  static constexpr bool known = true, heap = false;
  static void write(W& w, T* p) {
    if (!p) return w.null();
    if constexpr (!is_complete<U>::value) {
      return w.unknown();
    } else {
      State& s = S();
      auto a = reinterpret_cast<std::uintptr_t>(p);
      if (a % alignof(U)) return w.unknown();
      auto arr = s.arrays.find(a);
      if (arr != s.arrays.end() && arr->second.elem_size == sizeof(U)) {
        const ArrEntry& e = arr->second;
        return w.ref(p, e.type, e.fn, e.n, e.aux);
      }
      auto blk = s.blocks.find(a);
      if (blk != s.blocks.end()) {
        std::size_t size = blk->second.size;
        if (size >= 2 * sizeof(U) && size % sizeof(U) == 0)
          return w.ref(p, type_no<ArrOf<U>>(), &arr_thunk<U>, size / sizeof(U));
        return write_pointee<U>(w, p);
      }
      if (valid(a, sizeof(U))) return write_pointee<U>(w, p);
      w.unknown();
    }
  }
};

template <class X>
void W::value(const X& x) {
  using P = Plain<X>;
  if constexpr (Ser<P>::known) Ser<P>::write(*this, x);
  else unknown();
}

template <class X>
void W::field(const char* name, const X& x) {
  using P = Plain<X>;
  if constexpr (Ser<P>::known) {
    if (!first) *buf += ",";
    first = false;
    json_str(*buf, name, std::strlen(name));
    *buf += ":";
    Ser<P>::write(*this, x);
  }
}

template <class It>
void W::seq(const char* kind, It begin, It end) {
  *buf += "{\"kind\":\"";
  *buf += kind;
  *buf += "\",\"items\":[";
  std::size_t i = 0;
  for (; begin != end && i < MAX_ITEMS; ++begin, ++i) {
    if (i) *buf += ",";
    value(*begin);
  }
  *buf += "]}";
}

// ------------------------------------------------------------ trace output

// Process-level pieces (file descriptors, signals) live in cvt_support.cpp so
// that no POSIX header leaks names like `link` or `dup` into the snippet.
namespace sys {
void ensure_init();
void write_trace(const char* data, std::size_t n);
std::string read_stdout(bool tail);  // tail: last 4000 bytes; else new bytes
[[noreturn]] void exit_now(int code);
}  // namespace sys

inline void emit_line(std::string& line) {
  State& s = S();
  line.insert(line.begin(), '\x1e');
  line += '\n';
  sys::write_trace(line.data(), line.size());
  s.bytes += line.size();
}

inline void flush_program_output() {
  std::cout.flush();
  std::fflush(stdout);
}

inline std::string stdout_delta() { return sys::read_stdout(false); }
inline std::string stdout_tail() { return sys::read_stdout(true); }

inline void finish(const char* error) {
  State& s = S();
  if (s.done) return;
  s.done = true;
  s.inside = true;
  flush_program_output();
  std::string line = "{\"final\":true,\"truncated\":";
  line += s.truncated ? "true" : "false";
  line += ",\"error\":";
  if (error) json_str(line, error, std::strlen(error));
  else line += "null";
  line += ",\"stdout\":";
  std::string out = stdout_tail();
  json_str(line, out.data(), out.size());
  line += "}";
  emit_line(line);
}

inline void write_locals(W& w, const VarRec* begin, const VarRec* end, long frame, bool& first) {
  for (const VarRec* v = begin; v != end; ++v) {
    if (v->frame != frame || (v->flags & HIDDEN)) continue;
    if (!first) *w.buf += ",";
    first = false;
    json_str(*w.buf, v->name, std::strlen(v->name));
    *w.buf += ":";
    v->write(w, v->addr, v->n, v->aux);
  }
}

struct NoRet {};

template <class R>
void emit(int line, const char* event, const R* ret) {
  State& s = S();
  if (s.done || s.inside || s.frames.empty()) return;
  if (s.steps >= CVT_MAX_STEPS || s.bytes > MAX_TRACE_BYTES) {
    s.truncated = true;
    finish(nullptr);
    sys::exit_now(0);
  }
  s.inside = true;
  ++s.steps;
  std::string out, heap;
  out.reserve(1024);
  W w;
  w.buf = &out;
  out += "{\"line\":";
  out += std::to_string(line);
  out += ",\"event\":\"";
  out += event;
  out += "\",\"func\":";
  const FrameRec& top = s.frames.back();
  json_str(out, top.name, std::strlen(top.name));
  out += ",\"stack\":[";
  for (std::size_t i = 0; i < s.frames.size(); ++i) {
    if (i) out += ",";
    out += "{\"func\":";
    json_str(out, s.frames[i].name, std::strlen(s.frames[i].name));
    out += ",\"locals\":{";
    bool first = true;
    if (i == 0) {
      for (const VarRec& g : s.globals) {
        if (g.flags & HIDDEN) continue;
        if (!first) out += ",";
        first = false;
        json_str(out, g.name, std::strlen(g.name));
        out += ":";
        g.write(w, g.addr, g.n, g.aux);
      }
    }
    write_locals(w, s.vars.data(), s.vars.data() + s.vars.size(), static_cast<long>(i), first);
    out += "}}";
  }
  out += "]";
  if constexpr (!std::is_same<R, NoRet>::value) {
    out += ",\"return_value\":";
    if (ret) w.value(*ret);
    else out += "null";
  } else if (event[0] == 'r') {
    out += ",\"return_value\":null";
  }
  w.buf = &heap;
  for (std::size_t i = 0; i < w.queue.size(); ++i) {
    Pending p = w.queue[i];
    if (i) heap += ",";
    heap += "\"";
    heap += std::to_string(p.id);
    heap += "\":";
    w.first = true;
    p.fn(w, p.addr, p.n, p.aux);
  }
  out += ",\"heap\":{";
  out += heap;
  out += "}";
  flush_program_output();
  std::string delta = stdout_delta();
  if (!delta.empty()) {
    out += ",\"stdout\":";
    json_str(out, delta.data(), delta.size());
  }
  out += "}";
  emit_line(out);
  s.inside = false;
}

// ------------------------------------------------------- instrumentation API

inline void step(int line) { emit<NoRet>(line, "line", nullptr); }

inline void call() {
  State& s = S();
  if (!s.frames.empty()) emit<NoRet>(s.frames.back().line, "call", nullptr);
}

inline void retv(int line) { emit<NoRet>(line, "return", nullptr); }

template <class T>
void retval(int line, const T& v) {
  emit<Plain<T>>(line, "return", &v);
}

template <class T>
T&& ret(int line, T&& v) {
  using P = Plain<std::remove_reference_t<T>>;
  const P& ref = v;
  emit<P>(line, "return", &ref);
  return static_cast<T&&>(v);
}

struct Frame {
  bool active = false;
  Frame(const char* name, int line, bool is_main = false) {
    State& s = S();
    if (s.inside || s.done) return;
    sys::ensure_init();
    active = true;
    s.frames.push_back(FrameRec{name, line, is_main});
  }
  ~Frame() {
    if (!active) return;
    State& s = S();
    long depth = static_cast<long>(s.frames.size()) - 1;
    while (!s.vars.empty() && s.vars.back().frame >= depth) s.vars.pop_back();
    s.frames.pop_back();
  }
  Frame(const Frame&) = delete;
  Frame& operator=(const Frame&) = delete;
};

template <class T>
void var_thunk(W& w, const void* p, std::size_t, std::size_t) {
  Ser<Plain<T>>::write(w, *static_cast<const T*>(p));
}

template <class E>
void arr_var_thunk(W& w, const void* p, std::size_t n, std::size_t) {
  w.ref(p, type_no<ArrOf<E>>(), &arr_thunk<E>, n);
}

template <class E>
void arr2_var_thunk(W& w, const void* p, std::size_t rows, std::size_t cols) {
  w.ref(p, type_no<Arr2Of<E>>(), &arr2_thunk<E>, rows, cols);
}

// Registers one variable while it is in scope.
class Var {
 protected:
  long index_ = -1;
  bool global_ = false;
  std::uintptr_t lo_ = 0, hi_ = 0;
  unsigned flags_ = 0;
  bool registered_array_ = false;

  void add(const char* name, const void* addr, std::size_t size, ObjFn fn, std::size_t n,
           std::size_t aux, unsigned flags) {
    State& s = S();
    if (s.inside || s.done) return;
    flags_ = flags;
    lo_ = reinterpret_cast<std::uintptr_t>(addr);
    hi_ = lo_ + size;
    VarRec rec{name, addr, size, n, aux, fn, flags, static_cast<long>(s.frames.size()) - 1};
    if ((flags & GLOBAL) || s.frames.empty()) {
      global_ = true;
      rec.frame = -1;
      s.globals.push_back(rec);
      index_ = static_cast<long>(s.globals.size()) - 1;
    } else {
      s.vars.push_back(rec);
      index_ = static_cast<long>(s.vars.size()) - 1;
    }
  }
  void add_array(const void* addr, ArrEntry entry) {
    S().arrays[reinterpret_cast<std::uintptr_t>(addr)] = entry;
    registered_array_ = true;
  }

 public:
  Var() {}
  template <class T>
  Var(const char* name, T& ref, unsigned flags = 0) {
    if constexpr (Ser<Plain<T>>::known) {
      add(name, (const void*)std::addressof(ref), sizeof(T), &var_thunk<T>, 0, 0, flags);
    }
  }
  ~Var() {
    if (index_ < 0) return;
    State& s = S();
    if (global_) return;  // globals live for the whole run
    if (static_cast<long>(s.vars.size()) > index_) s.vars.resize(static_cast<std::size_t>(index_));
    if (registered_array_) {
      auto it = s.arrays.find(lo_);
      if (it != s.arrays.end()) s.arrays.erase(it);
    }
    if (flags_ & OWN) forget_ids(lo_, hi_);
  }
  Var(const Var&) = delete;
  Var& operator=(const Var&) = delete;
};

// A declared C array (also works for variable-length arrays).
class Arr : public Var {
 public:
  template <class E>
  Arr(const char* name, E* first, std::size_t n, unsigned flags = 0) {
    using P = Plain<E>;
    if constexpr (Ser<P>::known) {
      add(name, (const void*)first, n * sizeof(E), &arr_var_thunk<P>, n, 0, flags);
      if (index_ >= 0)
        add_array((const void*)first, ArrEntry{sizeof(E), n, 0, type_no<ArrOf<P>>(), &arr_thunk<P>});
    }
  }
};

// A declared 2-D C array, passed as &a[0][0], rows, cols.
class Arr2 : public Var {
 public:
  template <class E>
  Arr2(const char* name, E* first, std::size_t rows, std::size_t cols, unsigned flags = 0) {
    using P = Plain<E>;
    if constexpr (Ser<P>::known) {
      add(name, (const void*)first, rows * cols * sizeof(E), &arr2_var_thunk<P>, rows, cols, flags);
      if (index_ >= 0)
        add_array((const void*)first, ArrEntry{cols * sizeof(E), rows, cols, type_no<Arr2Of<P>>(), &arr2_thunk<P>});
    }
  }
};

}  // namespace cvt_rt
