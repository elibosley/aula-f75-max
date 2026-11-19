# Releases

Download desktop applications and model-specific firmware from [GitHub Releases](https://github.com/elibosley/aula-f75-max/releases). Each version provides:

- `F75-Studio-macos-arm64.zip`
- `F75-Studio-windows-x64.zip`
- `F75-Studio-linux-x64.tar.gz`
- `F75-Studio-firmware-f75max.zip`
- `F75-Studio-firmware-s75pro.zip`
- `release-manifest.json` and `SHA256SUMS`

Firmware archives contain BIN/ELF files, build and test receipts, exact corresponding project and dependency source, and their own checksums. Choose the archive for the keyboard model. The S75 Pro image is experimental; its physical hardware qualification is pending. Download availability does not enable one-click installation: the installer still requires a separately admitted, hardware-qualified bundle. This repository does not distribute supplier executables, supplier firmware, pairing credentials or private hardware captures.

## Version and publication flow

Use Conventional Commits (`feat:`, `fix:`, and `feat!:` for breaking changes). Release Please maintains a version PR with the package version, manifest and changelog. Merge that PR to create a draft GitHub release. The release workflow then calls the existing firmware and desktop workflows directly with the exact release SHA. It uses the built-in `GITHUB_TOKEN`; no personal token is required.

Both firmware targets build twice from clean objects. F75 retains its two build profiles and full existing focused suite. S75 builds its portrait profile and runs recovery, USB, panel, input, settings, radio framing, custom controls, gauge and idle/wake checks in emulation. Desktop builds run on macOS, Windows and Linux, and each packaged application runs its shell check.

Publication requires every job to pass. The assembler rejects missing archives, changed hashes, different commits or versions, incomplete firmware proof, and missing corresponding source. It writes a combined manifest and SHA256SUMS. The publisher uploads the complete set to the draft, checks GitHub's stored SHA-256 digests and byte sizes, then publishes a prerelease. It verifies the resulting Git tag resolves to the built SHA. Existing public releases are never overwritten. Releases stay prereleases while the project uses development firmware and S75 hardware qualification is open.

The repository must allow GitHub Actions to create pull requests in Settings → Actions → General. Workflow permissions are scoped in YAML: build jobs have read access; Release Please has contents/issues/pull-request write access; only publication gets contents write access. Repository admins enable the create-PR setting during setup.

GitHub does not start normal PR or tag workflows for events created with its built-in token. Release artifact jobs are direct reusable-workflow calls in the originating run, so they do not depend on those suppressed events. The complete release commit is tested before publication.

## Recover a failed release build

A failed build or upload leaves the release as a draft. Use Actions → Build and publish release artifacts → Run workflow. Supply the existing draft tag and its exact full release commit SHA. The package version at that SHA must match the tag. The workflow rebuilds and verifies all assets, then replaces partial assets only while the release remains a draft. No published release assets or Git tags are moved.

For local packaging, commit source changes first. `release_artifacts.py stamp` and `package_builds.py` reject a dirty source tree. This keeps the corresponding source archive consistent with the released binaries.
