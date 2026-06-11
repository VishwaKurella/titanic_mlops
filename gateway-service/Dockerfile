# ── Stage 1: build ────────────────────────────────────────────────────────────
# Use the official Rust image pinned to a specific version for reproducibility.
# slim variant saves ~600MB vs full image.
FROM rust:1.88-slim AS builder

WORKDIR /app

# Install only what's needed to link against OpenSSL (reqwest uses it)
RUN apt-get update && apt-get install -y --no-install-recommends \
    pkg-config \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# ── Dependency caching trick ───────────────────────────────────────────────────
# Copy manifests first and build a fake main.rs.
# Docker caches this layer as long as Cargo.toml/Cargo.lock don't change,
# so iterative rebuilds only recompile your code, not all dependencies.
COPY Cargo.toml Cargo.lock ./
RUN mkdir src && echo "fn main() {}" > src/main.rs
RUN cargo build --release
RUN rm src/main.rs

# Now copy real source and build — only this layer reruns on code changes
COPY src ./src
# Touch main.rs so cargo knows it changed (the dummy build above cached deps)
RUN touch src/main.rs && cargo build --release

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
# distroless/cc contains only the C runtime — no shell, no package manager,
# no utilities. Attack surface is minimal.
FROM gcr.io/distroless/cc-debian12:nonroot

WORKDIR /app

# Copy only the compiled binary — nothing else from the build stage
COPY --from=builder /app/target/release/gateway-service .

# distroless/cc:nonroot runs as uid 65532 (nonroot) by default — no root

EXPOSE 8080

CMD ["./gateway-service"]