# Bounded notification frame validation

The prepared `notification-frames` target calls the repository-owned
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

## Release integration design

The shared beta/RC lifecycle must package an explicit allowlist of portable owned
source modules, required resources and synthetic tests. It must not archive the
whole household configuration, runtime state, installation receipts, credentials,
real frames or generated exports. Child automation/script libraries and upstream
quirks retain their own versions; a source bundle needs its own version identity,
archive checks and receipt. Existing build/verification tools remain validation
inputs, and must not become implicit deployment or promotion actions.

This target is prepared but not yet wired to a shared RC workflow. Adoption must
preserve the current required CI checks, pin a durable toolkit merge commit and
bind actual Linux results to a frozen candidate plan. Installation-specific
acceptance remains separate; no production action or stable publication is part
of this preparation.
