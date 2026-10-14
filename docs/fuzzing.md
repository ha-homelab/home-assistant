# Bounded notification frame validation

The `notification-frames` target calls the repository-owned
`NotificationFrameCache.feed` parser with arbitrary bounded chunks. Every input
gets a new explicitly supplied temporary root; the default runtime cache path is
never used. Assertions cover retained-buffer bounds, source-frame bytes, JPEG
markers, event ownership, private file permissions, temporary-file cleanup and
close cleanup. An oversized synthetic chunk exercises the existing reset limit.
No camera connection, HA runtime, real media, existing cache or configuration
file is read. Seed media consists only of JPEG marker bytes and synthetic text;
it is not a household image or a claim of a decodable photograph.

The committed target allows 60 seconds and a 4096-byte input limit, with a
hash-locked Linux/x86-64 Atheris 3.1.0 dependency. Existing tests replay the seed
corpus without the engine. A local corpus replay is not a completed Linux fuzz
qualification run.

```sh
python3 -m unittest discover -s tests -p test_fuzz_oracle.py -v
```

The existing notification subscription, rendering, configuration and runtime
checks remain required. Parser qualification does not prove live camera quality,
phone notification delivery or deployment acceptance.

## Release integration

The shared RC workflow requires this real Linux campaign and binds its result to
the exact source and frozen version plan. Missing or failed fuzz evidence stops
RC publication. The release assets package only the portable frame-cache library;
see [packaging and acceptance](release-packaging.md) for the explicit source
inventory and separate installation requirements. Beta builds retain all normal
quality checks and do not claim RC mutation evidence.
