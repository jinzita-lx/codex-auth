#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

prefix="$tmp/prefix with spaces"
codex_home="$tmp/codex-home"

CODEX_AUTH_PREFIX="$prefix" "$repo_root/install.sh" >/dev/null

wrapper="$prefix/bin/codex-auth"
project_dir="$prefix/share/codex-auth"

[[ -x "$wrapper" ]]
[[ -d "$project_dir/codex_auth" ]]
[[ ! -L "$wrapper" ]]

CODEX_HOME="$codex_home" "$wrapper" --help >/dev/null
CODEX_HOME="$codex_home" "$wrapper" path >/dev/null
CODEX_AUTH_PROJECT="$project_dir" "$project_dir/bin/codex-auth" --help >/dev/null

old_prefix="$tmp/old-prefix"
old_project_dir="$old_prefix/share/codex-auth"
old_wrapper="$old_prefix/bin/codex-auth"

mkdir -p "$old_project_dir/bin" "$old_prefix/bin"
cp -R "$repo_root"/. "$old_project_dir/"
ln -s "$old_project_dir/bin/codex-auth" "$old_wrapper"

CODEX_AUTH_PREFIX="$old_prefix" "$old_project_dir/install.sh" >/dev/null

[[ -x "$old_wrapper" ]]
[[ ! -L "$old_wrapper" ]]
grep -q "resolve_script_dir" "$old_project_dir/bin/codex-auth"
CODEX_HOME="$codex_home" "$old_wrapper" --help >/dev/null
