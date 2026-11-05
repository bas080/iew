# Language Selection Research & Decision: Standalone `iew-lsp`

## 1. Executive Summary

The objective of this research is to evaluate candidate languages for rewriting `iew` into a standalone, single-binary executable that can be placed on a user's `PATH` and executed without external runtime dependencies (such as Python, node_modules, or shared libraries).

The target is to support major consumer and developer platforms (Linux x86_64/arm64, macOS x86_64/arm64, and Windows x86_64), while keeping the codebase **highly readable, idiomatic, and easy to maintain** by any engineer.

After analyzing the trade-offs across candidate ecosystems (Go, Rust, Zig, C++, and bundled runtimes such as Bun/PyInstaller), **Go** was selected as the optimal choice.

---

## 2. Evaluation Criteria

1. **Standalone Binary & Portability**:
   - Must produce a single, self-contained executable with zero or minimal OS runtime dependencies.
   - Ease of cross-compiling for Linux (glibc & musl), macOS (Universal Darwin), and Windows.
2. **Readability & Maintainability**:
   - Clean, readable syntax with minimal boilerplate.
   - Standardized formatting and idioms (`gofmt`, clear error handling).
   - Low cognitive overhead for future maintainers.
3. **Concurrency & LSP Suitability**:
   - LSP servers require concurrent asynchronous operations: reading JSON-RPC over stdio, non-blocking timers for debouncing reviews, and background HTTP calls to LLM inference endpoints.
4. **Ecosystem & Standard Library**:
   - Strong native support for JSON, HTTP client/server, subprocess/stdio streaming, and file I/O without requiring complex third-party frameworks.

---

## 3. Candidate Comparison

| Metric / Criteria | Go | Rust | Zig | Bundled Runtimes (Bun/PyInstaller) |
|---|---|---|---|---|
| **Standalone Distribution** | Native single binary, static linking by default (or pure cgo-free build) | Native single binary, statically linked (or musl target) | Native single binary, zero libc dependency available | Packaged binary containing bundled runtime & zipfs |
| **Cross-Compilation** | Exceptional (`GOOS=... GOARCH=... go build` out of the box) | Good (requires target toolchains, e.g. `cross` or target sysroots) | Excellent (built-in C/C++ cross-compiler) | Difficult or requires running bundling step on target OS |
| **Readability & Simplicity** | Very high; clean procedural style, standard idioms, simple control flow | Medium; steep learning curve (lifetimes, traits, macros, async runtimes) | Medium; manual memory management, explicit allocators | High; but fragile packaging layers |
| **Concurrency Model** | Goroutines, channels, and `time.Timer` — perfectly suited for debounced LSP | Tokio / async runtimes; powerful but adds async stack complexity | Manual threads/event loops; lacks mature async runtime | Event loop based (Node/Bun) or threads (Python) |
| **Stdlib Completeness** | `net/http`, `encoding/json`, `os/exec`, `sync` built-in; only TOML needed | Minimal stdlib; requires serde, reqwest, tokio, etc. | Minimal stdlib; networking and HTTP APIs still evolving | Full stdlib, but larger binary overhead |
| **Binary Size** | ~10 MB - 15 MB (compressible to ~4 MB with strip/upx) | ~3 MB - 8 MB | ~2 MB - 5 MB | ~50 MB - 90 MB |
| **Long-Term Maintenance** | Easiest; consistent across Go versions, predictable codebase | Higher maintenance cost; frequent dependency updates | Higher risk; language and standard library still pre-1.0 | High maintenance; runtime packager breakages |

---

## 4. In-Depth Analysis of Candidates

### A. Go (Chosen)
- **Why it fits best**:
  - Go's standard library provides high-quality implementations of `net/http` (with connection pooling, timeouts, and streaming), `encoding/json`, and `os/exec`.
  - The LSP concurrency model (handling stdio while managing debounced background worker routines) maps directly to Go's lightweight goroutines and `sync.Mutex` / `time.Timer`.
  - Go's cross-compilation is unmatched in developer ergonomics: compiling for macOS arm64, Linux amd64, or Windows is as simple as setting `GOOS` and `GOARCH`.
  - Code readability is paramount: Go has virtually no hidden control flow, explicit error handling, and rigid standard conventions (`gofmt`). Any developer can read, understand, and modify it immediately.

### B. Rust
- **Pros**:
  - Zero-cost abstractions, excellent memory footprint, strong type safety.
  - Popular crates exist for LSP (`tower-lsp` or `lsp-types`).
- **Cons**:
  - Higher cognitive overhead: async Rust (Tokio) introduces pin projections, lifetime annotations, and complex error trait hierarchies.
  - Cross-compilation across platforms often requires containerized builds or target toolchain installations (`rustup target add ...` + linker configuration).
  - Significantly higher barrier to entry for maintenance compared to Go.

### C. Bundled Runtimes (Bun compile / PyInstaller / Deno compile)
- **Pros**:
  - Can reuse existing TypeScript or Python logic directly.
- **Cons**:
  - Binaries are effectively self-extracting zip archives containing full runtime engines (V8/Bun/Python interpreter), resulting in binary sizes of 50–90+ MB.
  - Can suffer from extraction overhead, antivirus false-positives on Windows, and compatibility issues across diverse glibc environments.
  - Does not satisfy the goal of a clean, native, standalone executable.

---

## 5. Decision & Architecture

**Decision**: Rewrite `iew-lsp` in **Go**.

### Architecture Overview
1. **Module**: `github.com/iew-org/iew`
2. **Directory Structure**:
   - `cmd/iew-lsp/main.go`: CLI entrypoint implementing standard LSP stdio server and `--health` diagnostic check.
   - `internal/config`: Loads TOML config (`~/.config/iew/iew.toml` or `$IEW_CONFIG`), matching all root and `[request]` options with sane defaults.
   - `internal/prompt`: Template interpolation and default review prompt construction.
   - `internal/format`: Line coordinate parsing (`<line>: <message>`).
   - `internal/adapter`: Inference adapters for Ollama (`/api/generate`) and OpenRouter (`/api/v1/chat/completions`) with exponential backoff and timeout handling.
   - `internal/lsp`: JSON-RPC 2.0 stdio framing, document synchronization (`didOpen`, `didChange`, `didSave`, `didClose`), debounced review scheduling, and diagnostic publication.
3. **Output Binary**: `bin/iew-lsp` (drop-in replacement for existing configurations).
