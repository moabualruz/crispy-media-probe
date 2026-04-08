# crispy-media-probe

Media probing helpers built around ffprobe, ffmpeg, and optional libmpv integration.

## What This Crate Is

`crispy-media-probe` inspects IPTV/media streams and captures screenshots using common external media tools. It is designed for diagnostics, validation pipelines, and automated media QA.

## What It Provides

- stream probing via ffprobe
- audio/video metadata extraction
- screenshot capture via ffmpeg
- HLS variant parsing and selection helpers
- bitrate profiling
- label-vs-resolution mismatch checks
- optional libmpv-based probe/screenshot path

## Installation

```toml
[dependencies]
crispy-media-probe = "0.1.1"
```

Optional feature:

```toml
[dependencies]
crispy-media-probe = { version = "0.1.1", features = ["libmpv-backend"] }
```

MSRV: Rust `1.85`

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

Depending on which API path you use, you may need:

- `ffprobe`
- `ffmpeg`
- `libmpv` when `libmpv-backend` is enabled

## Typical Uses

- stream diagnostics
- validation pipelines
- screenshot generation
- automated media QA

## Current Limitations

- external binaries are not bundled by the crate
- platform support depends on the caller providing working ffmpeg/ffprobe/libmpv installations
- this crate does not queue, persist, or orchestrate probe jobs

## License

See `LICENSE.md` and `NOTICE.md`.
