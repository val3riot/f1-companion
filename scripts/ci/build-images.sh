#!/usr/bin/env bash
set -Eeuo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
: "${API_IMAGE:?API_IMAGE is required}"
: "${FRONTEND_IMAGE:?FRONTEND_IMAGE is required}"
: "${IMAGE_TAG:?IMAGE_TAG is required}"

push="${PUSH_IMAGES:-false}"
platforms="${PLATFORMS:-linux/amd64}"
cache_args=()

if [[ -n "${BUILDX_CACHE_FROM:-}" ]]; then
  cache_args+=(--cache-from "$BUILDX_CACHE_FROM")
fi
if [[ -n "${BUILDX_CACHE_TO:-}" ]]; then
  cache_args+=(--cache-to "$BUILDX_CACHE_TO")
fi

output_arg=(--load)
if [[ "$push" == "true" ]]; then
  output_arg=(--push)
fi

build_image() {
  local image="$1"
  local context_dir="$2"
  local build_args=(
    --platform "$platforms"
    --file "$repo_dir/$context_dir/Dockerfile"
    --tag "$image:$IMAGE_TAG"
  )

  if ((${#cache_args[@]})); then
    build_args+=("${cache_args[@]}")
  fi
  build_args+=("${output_arg[@]}")

  docker buildx build \
    "${build_args[@]}" \
    "$repo_dir/$context_dir"
}

build_image "$API_IMAGE" backend
build_image "$FRONTEND_IMAGE" frontend
