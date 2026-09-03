# Windows release packaging target

This folder documents the post-prototype packaging direction. It is **not** required to run build 0.12.

Release goals:
- `ElectionLab.exe` launches directly with no console window.
- Python/PySide dependencies are bundled; the user does not install or manage a venv.
- Start Menu/Desktop shortcuts are created by an installer.
- Immutable app/runtime files are separated from the mutable `ElectionLabData` root.
- The data root can live outside the app runtime and can contain large local-AI models/caches.
- Updates preserve `portable_config.json`, user data and portable campaign saves.
- Prefer a one-folder packaged runtime for predictable startup/repair; the installer can make it feel like a normal single application to the user.

A Windows release builder can use PyInstaller/Nuitka or another GUI-subsystem bundler. Do not enable a console window in the end-user executable.
