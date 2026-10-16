# File Transfer

> **Read this file when** you need to push or pull files to/from a device (shared storage or
> app-private storage). Use shared storage for files accessible to all apps. App-private storage
> uses root when available and otherwise uses `run-as` for debuggable apps.

Commands to push/pull files to shared storage (sdcard) and app-private storage. All commands accept
**either** `--device <serial>` **or** `--session <session_id>`.

## Shared Storage (sdcard)

```bash
# Push local file -> /sdcard/Download/<name>
android-emu-agent file push ./sample.json --device emulator-5554

# Push to a specific path
android-emu-agent file push ./sample.json --device emulator-5554 --remote /sdcard/Download/sample.json

# Pull from shared storage
android-emu-agent file pull /sdcard/Download/sample.json --device emulator-5554
```

## App-Private Storage

Rooted targets can access any app sandbox. On non-root targets, the app must be debuggable so
Android's `run-as` command can enter its sandbox.

```bash
# Push into app files/ (default)
android-emu-agent file app push com.example.app ./config.json --device emulator-5554

# Push to a specific app-private path
android-emu-agent file app push com.example.app ./config.json --device emulator-5554 --remote files/config.json

# Pull app-private file or directory
android-emu-agent file app pull com.example.app files/ --device emulator-5554
```

Outputs land in `~/.android-emu-agent/artifacts/files` unless you provide `--local`. Automatically
generated pull paths include a random UUID, so repeated or concurrent pulls keep separate files or
directories even within the same second. Use the returned path rather than reconstructing a
timestamp-based filename. Long descriptive names are shortened to keep generated filename components
within 255 UTF-8 bytes while retaining the full UUID. An explicit `--local` retains the existing
replacement or directory-merge behavior; choose different destinations to preserve each result.

App-private transfers that require on-device staging use a separate random name for each transfer.
Cleanup removes only that transfer's staging path. This does not serialize transfers to an
explicitly shared destination or make a directory copy atomic.

## Find Files/Folders

`file find` searches a directory tree and returns metadata for matching files or folders. It works
without root for paths readable by the Android shell user; protected paths still require root.

```bash
# Find all SQLite files under app data
android-emu-agent file find /data/data --name "*.db" --type file --max-depth 6 --device emulator-5554

# Find directories named "cache" under shared storage
android-emu-agent file find /sdcard --name "cache" --type dir --max-depth 4 --device emulator-5554
```

The output includes: path, type, size (bytes), mode, uid:gid, and mtime (epoch).

## List Directory

`file list` follows the same access rules: shell-readable paths work without root, while protected
paths require root.

```bash
# List immediate entries in a directory
android-emu-agent file list /data/data --device emulator-5554

# List only folders
android-emu-agent file list /sdcard --type dir --device emulator-5554
```

The output includes: path, type, size (bytes), mode, uid:gid, and mtime (epoch).
