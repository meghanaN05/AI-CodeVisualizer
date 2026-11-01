// Process-level half of the trace runtime, compiled once into an object file
// and linked with every instrumented snippet (see cvt_runtime.hpp).
//
//  * The trace goes to the ORIGINAL stdout (a dup of fd 1); the program's
//    own stdout is redirected to a temp file and reported per step.
//  * Fatal signals, uncaught exceptions and exit() still write the final
//    record, so a crash yields the steps so far plus an error.
//  * Global operator new/delete are replaced to track live heap blocks.
#include "cvt_runtime.hpp"

#include <cxxabi.h>
#include <fcntl.h>
#include <signal.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

#include <typeinfo>

namespace cvt_rt {
namespace {

const char* signal_message(int sig) {
  switch (sig) {
    case SIGSEGV: return "Segmentation fault (invalid memory access)";
    case SIGBUS: return "Bus error (invalid memory access)";
    case SIGFPE: return "Floating point exception (e.g. division by zero)";
    case SIGABRT: return "Aborted (assertion failed or std::abort)";
    case SIGILL: return "Illegal instruction";
    case SIGXCPU: return "CPU time limit exceeded";
    default: return "Killed by a signal";
  }
}

void on_signal(int sig) {
  State& s = S();
  alarm(2);  // never hang here if the crash left stdio locked
  if (!s.done) {
    std::string msg = signal_message(sig);
    if (s.inside) msg += " while reading program state";
    s.inside = false;
    finish(msg.c_str());
  }
  _exit(128 + sig);
}

void on_terminate() {
  std::string msg = "Uncaught exception";
  try {
    if (auto e = std::current_exception()) std::rethrow_exception(e);
  } catch (const std::exception& e) {
    int status = 0;
    char* type = abi::__cxa_demangle(typeid(e).name(), nullptr, nullptr, &status);
    msg += " ";
    msg += status == 0 && type ? type : "std::exception";
    std::free(type);
    msg += ": ";
    msg += e.what();
  } catch (...) {
  }
  S().inside = false;
  finish(msg.c_str());
  _exit(134);
}

void on_exit() { finish(nullptr); }

char altstack[1 << 16];

}  // namespace

namespace sys {

void ensure_init() {
  State& s = S();
  if (s.initialized) return;
  s.initialized = true;
  std::fflush(stdout);
  // fcntl/fwrite rather than dup/write: a snippet's global `int dup;` is an
  // unmangled symbol that would shadow libc's function at link time.
  s.trace_fd = fcntl(1, F_DUPFD, 0);
  if (std::FILE* tmp = std::tmpfile()) {
    s.out_fd = fcntl(fileno(tmp), F_DUPFD, 0);
    dup2(fileno(tmp), 1);
  }
  stack_t ss{};
  ss.ss_sp = altstack;
  ss.ss_size = sizeof altstack;
  sigaltstack(&ss, nullptr);
  struct sigaction sa {};
  sa.sa_handler = on_signal;
  sa.sa_flags = SA_ONSTACK;
  sigemptyset(&sa.sa_mask);
  for (int sig : {SIGSEGV, SIGBUS, SIGFPE, SIGABRT, SIGILL, SIGXCPU}) sigaction(sig, &sa, nullptr);
  std::set_terminate(on_terminate);
  std::atexit(on_exit);
}

void write_trace(const char* p, std::size_t n) {
  static std::FILE* out = nullptr;
  if (!out) {
    out = fdopen(S().trace_fd >= 0 ? S().trace_fd : 1, "w");
    if (!out) return;
  }
  std::fwrite(p, 1, n, out);
  std::fflush(out);
}

std::string read_stdout(bool tail) {
  State& s = S();
  std::string out;
  struct stat st;
  if (s.out_fd < 0 || fstat(s.out_fd, &st) != 0) return out;
  long long size = st.st_size;
  long long limit = tail ? 4000 : static_cast<long long>(MAX_STDOUT_DELTA);
  long long from = tail ? 0 : s.printed;
  if (size <= from) return out;
  if (size - from > limit) from = size - limit;
  out.resize(static_cast<std::size_t>(size - from));
  ssize_t k = pread(s.out_fd, &out[0], out.size(), static_cast<off_t>(from));
  out.resize(k > 0 ? static_cast<std::size_t>(k) : 0);
  if (!tail) s.printed = size;
  return out;
}

void exit_now(int code) { _exit(code); }

}  // namespace sys
}  // namespace cvt_rt

// Replaced global allocation functions: record live heap blocks.
void* operator new(std::size_t n) {
  void* p = std::malloc(n ? n : 1);
  if (!p) throw std::bad_alloc();
  cvt_rt::on_alloc(p, n);
  return p;
}
void* operator new[](std::size_t n) {
  void* p = std::malloc(n ? n : 1);
  if (!p) throw std::bad_alloc();
  cvt_rt::on_alloc(p, n);
  return p;
}
void* operator new(std::size_t n, const std::nothrow_t&) noexcept {
  void* p = std::malloc(n ? n : 1);
  cvt_rt::on_alloc(p, n);
  return p;
}
void* operator new[](std::size_t n, const std::nothrow_t&) noexcept {
  void* p = std::malloc(n ? n : 1);
  cvt_rt::on_alloc(p, n);
  return p;
}
void operator delete(void* p) noexcept {
  cvt_rt::on_free(p);
  std::free(p);
}
void operator delete[](void* p) noexcept {
  cvt_rt::on_free(p);
  std::free(p);
}
void operator delete(void* p, std::size_t) noexcept {
  cvt_rt::on_free(p);
  std::free(p);
}
void operator delete[](void* p, std::size_t) noexcept {
  cvt_rt::on_free(p);
  std::free(p);
}
void operator delete(void* p, const std::nothrow_t&) noexcept {
  cvt_rt::on_free(p);
  std::free(p);
}
void operator delete[](void* p, const std::nothrow_t&) noexcept {
  cvt_rt::on_free(p);
  std::free(p);
}
