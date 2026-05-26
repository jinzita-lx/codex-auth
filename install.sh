#!/usr/bin/env bash
set -euo pipefail

repo="${CODEX_AUTH_REPO:-jinzita-lx/codex-auth}"
ref="${CODEX_AUTH_REF:-v0.1.2}"
prefix="${CODEX_AUTH_PREFIX:-"$HOME/.local"}"
project_dir="${CODEX_AUTH_PROJECT_DIR:-"$prefix/share/codex-auth"}"
bin_dir="${CODEX_AUTH_BIN_DIR:-"$prefix/bin"}"
install_tmp=""

log() {
  printf 'codex-auth install: %s\n' "$*" >&2
}

die() {
  printf 'codex-auth install: %s\n' "$*" >&2
  exit 1
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

copy_project() {
  local src="$1"
  local dst="$2"

  rm -rf "$dst"
  mkdir -p "$dst"

  local item
  for item in README.md README.en.md CHANGELOG.md pyproject.toml install.sh bin codex_auth docs; do
    if [[ -e "$src/$item" ]]; then
      cp -R "$src/$item" "$dst/"
    fi
  done
}

download_with_curl() {
  local src="$1"
  local archive="$2"
  local header=()

  if [[ -n "${GH_TOKEN:-}" ]]; then
    header=(-H "Authorization: Bearer $GH_TOKEN")
  elif [[ -n "${GITHUB_TOKEN:-}" ]]; then
    header=(-H "Authorization: Bearer $GITHUB_TOKEN")
  fi

  local tag_url="https://github.com/$repo/archive/refs/tags/$ref.tar.gz"
  local branch_url="https://github.com/$repo/archive/refs/heads/$ref.tar.gz"

  if curl -fsSL "${header[@]}" "$tag_url" -o "$archive"; then
    tar -xzf "$archive" -C "$src" --strip-components 1
    return 0
  fi

  if curl -fsSL "${header[@]}" "$branch_url" -o "$archive"; then
    tar -xzf "$archive" -C "$src" --strip-components 1
    return 0
  fi

  return 1
}

resolve_source() {
  local tmp="$1"
  local script_path="${BASH_SOURCE[0]:-}"

  if [[ -n "$script_path" && -f "$script_path" ]]; then
    local script_dir
    script_dir="$(cd "$(dirname "$script_path")" && pwd)"
    if [[ -f "$script_dir/pyproject.toml" && -d "$script_dir/codex_auth" ]]; then
      printf '%s\n' "$script_dir"
      return 0
    fi
  fi

  local src="$tmp/src"
  mkdir -p "$src"

  if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    log "downloading $repo@$ref with gh"
    if ! gh repo clone "$repo" "$src" -- --depth 1 --branch "$ref" >/dev/null 2>&1; then
      rm -rf "$src"
      gh repo clone "$repo" "$src" -- --depth 1 >/dev/null

      if ! git -C "$src" checkout "$ref" >/dev/null 2>&1; then
        git -C "$src" fetch --depth 1 origin "refs/tags/$ref:refs/tags/$ref" >/dev/null 2>&1 || true
        git -C "$src" checkout "$ref" >/dev/null 2>&1 || {
          git -C "$src" fetch --depth 1 origin "$ref" >/dev/null 2>&1 || true
          git -C "$src" checkout FETCH_HEAD >/dev/null 2>&1 || die "could not checkout ref: $ref"
        }
      fi
    fi
    printf '%s\n' "$src"
    return 0
  fi

  if command -v git >/dev/null 2>&1; then
    log "downloading $repo@$ref with git"
    if git clone --depth 1 --branch "$ref" "https://github.com/$repo.git" "$src" >/dev/null 2>&1; then
      printf '%s\n' "$src"
      return 0
    fi
  fi

  if command -v curl >/dev/null 2>&1 && command -v tar >/dev/null 2>&1; then
    log "downloading $repo@$ref with curl"
    if download_with_curl "$src" "$tmp/source.tar.gz"; then
      printf '%s\n' "$src"
      return 0
    fi
  fi

  die "could not download $repo@$ref; for private repos, install GitHub CLI and run gh auth login"
}

main() {
  need_cmd python3

  install_tmp="$(mktemp -d)"
  trap 'rm -rf "$install_tmp"' EXIT

  local src
  src="$(resolve_source "$install_tmp")"
  [[ -f "$src/pyproject.toml" && -d "$src/codex_auth" ]] || die "invalid source tree: $src"

  log "checking Python modules"
  python3 -m compileall -q "$src/codex_auth"

  local stage="$install_tmp/codex-auth"
  copy_project "$src" "$stage"

  log "installing project to $project_dir"
  mkdir -p "$(dirname "$project_dir")"
  rm -rf "$project_dir"
  mv "$stage" "$project_dir"
  chmod 700 "$project_dir/bin/codex-auth"

  log "linking executable to $bin_dir/codex-auth"
  mkdir -p "$bin_dir"
  ln -sfn "$project_dir/bin/codex-auth" "$bin_dir/codex-auth"

  "$bin_dir/codex-auth" --help >/dev/null

  case ":$PATH:" in
    *":$bin_dir:"*) ;;
    *) log "warning: $bin_dir is not in PATH" ;;
  esac

  log "installed successfully"
  "$bin_dir/codex-auth" path
}

main "$@"
