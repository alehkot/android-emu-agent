# File Transfer

> **Read this file when** you need to push or pull files to/from a device (shared storage or
> app-private storage). Use shared storage for files accessible to all apps. Use app-private storage
> for config/data within a specific app's sandbox (requires root or emulator).

Commands to push/pull files to shared storage (sdcard) and app-private storage (rooted/emulator).
All commands accept **either** `--device <serial>` **or** `--session <session_id>`.

## Shared Storage (sdcard)

```bash
# Push local file -> /sdcard/Download/<name>
uv run android-emu-agent file push ./sample.json --device emulator-5554

# Push to a specific path
uv run android-emu-agent file push ./sample.json --device emulator-5554 --remote /sdcard/Download/sample.json

# Pull from shared storage
uv run android-emu-agent file pull /sdcard/Download/sample.json --device emulator-5554
```

## App-Private Storage (Rooted/Emulator)

```bash
# Push into app files/ (default)
uv run android-emu-agent file app push com.example.app ./config.json --device emulator-5554

# Push to a specific app-private path
uv run android-emu-agent file app push com.example.app ./config.json --device emulator-5554 --remote files/config.json

# Pull app-private file or directory
uv run android-emu-agent file app pull com.example.app files/ --device emulator-5554
```

Outputs land in `~/.android-emu-agent/artifacts/files` unless you provide `--local`.

## Find Files/Folders (Rooted/Emulator)

`file find` searches a directory tree and returns metadata for matching files or folders.

```bash
# Find all SQLite files under app data
uv run android-emu-agent file find /data/data --name "*.db" --type file --max-depth 6 --device emulator-5554

# Find directories named "cache" under shared storage
uv run android-emu-agent file find /sdcard --name "cache" --type dir --max-depth 4 --device emulator-5554
```

The output includes: path, type, size (bytes), mode, uid:gid, and mtime (epoch).

## List Directory (Rooted/Emulator)

```bash
# List immediate entries in a directory
uv run android-emu-agent file list /data/data --device emulator-5554

# List only folders
uv run android-emu-agent file list /sdcard --type dir --device emulator-5554
```

The output includes: path, type, size (bytes), mode, uid:gid, and mtime (epoch).
