# crispy-media-probe

Media probing helpers built around ffprobe, ffmpeg, and optional libmpv integration.

## Status

Extracted from CrispyTivi. Intended as a reusable Rust crate for stream inspection and screenshot capture.

## What This Crate Provides

- ffprobe-based media probing
- ffmpeg-based screenshot capture
- HLS variant inspection helpers
- bitrate profiling
- optional libmpv backend for environments that bundle mpv
- resolution mismatch checks

## Installation

```toml
[dependencies]
crispy-media-probe = "0.1"
```

Optional feature:

```toml
[dependencies]
crispy-media-probe = { version = "0.1", features = ["libmpv-backend"] }
```

## Quick Start

```rust
use crispy_media_probe::probe_stream;

# async fn demo() -> Result<(), Box<dyn std::error::Error>> {
let info = probe_stream("http://example.com/stream.m3u8", 10).await?;
println!("streams found: {}", info.stream_count);
# Ok(())
# }
```

## Runtime Requirements

Depending on the path used, callers may need:
- `ffprobe`
- `ffmpeg`
- `libmpv`

These requirements must be documented explicitly in the final public repo.

## Primary Use Cases

- stream diagnostics
- validation pipelines
- screenshot generation
- automated media QA

## Caveats

- this crate needs strongest runtime/platform documentation before public release
