# Where the price feed lives, sourced by every workflow step that reads or
# writes it. One place, so no step can quietly go back to the public remote.
#
# WHY A PRIVATE REPOSITORY. This repository is public. A `price-feed` branch
# here is a permanent, downloadable file of captured odds (book, price, line,
# capture time), and The Odds API's terms forbid redistributing its data as
# downloadable files that serve as raw data. The NHL lab found the same thing
# and moved its closing lines to a private repository on 2026-10-01. EPL's
# feed moved on 2026-10-31 (Cooper chose it from the NHL/CBB comparison).
#
# THE SECRET: `EPL_PRICE_FEED_TOKEN`, a fine-grained token limited to
# cooperross399/epl-price-feed with Contents read and write. Without it
# nothing is written anywhere: the feed is never published back to the
# public repository.
#
# THE LEGACY READ. Until the public `price-feed` branch is deleted, a fetch
# that finds nothing in the private repository reads it, so the first write
# carries the whole history across. Reading something already public
# publishes nothing new. Writes go to the private repository only.
#
# The bought historical odds (`odds-history`, Harvest Historical BTTS) are
# the same kind of file and live in the same private repository: set
# FEED_BRANCH=odds-history before calling.
#
# Usage (bash):  . scripts/price_feed_remote.sh
#                feed_fetch [--depth=1]  -> refs/$FEED_BRANCH-tip, exit 0 if found
#                feed_push <commit>      -> refs/heads/$FEED_BRANCH, private only

PRICE_FEED_REPO="cooperross399/epl-price-feed"
FEED_BRANCH="${FEED_BRANCH:-price-feed}"

feed_remote() {
  if [ -n "${EPL_PRICE_FEED_TOKEN:-}" ]; then
    printf 'https://x-access-token:%s@github.com/%s' "$EPL_PRICE_FEED_TOKEN" "$PRICE_FEED_REPO"
  fi
}

feed_fetch() {
  local remote
  remote=$(feed_remote)
  if [ -n "$remote" ] && git fetch --no-tags "$@" "$remote" +refs/heads/${FEED_BRANCH}:refs/${FEED_BRANCH}-tip 2>/dev/null; then
    return 0
  fi
  if [ -z "$remote" ]; then
    echo "::warning::EPL_PRICE_FEED_TOKEN is not set, so the private price feed ($PRICE_FEED_REPO) cannot be read or written."
  fi
  # Legacy, read-only: the public branch this feed used to live on.
  if [ -n "${GH_TOKEN:-}" ] && [ -n "${GITHUB_REPOSITORY:-}" ]; then
    git fetch --no-tags "$@" "https://x-access-token:${GH_TOKEN}@github.com/${GITHUB_REPOSITORY}" \
      +refs/heads/${FEED_BRANCH}:refs/${FEED_BRANCH}-tip 2>/dev/null && return 0
  fi
  return 1
}

feed_push() {
  local remote
  remote=$(feed_remote)
  if [ -z "$remote" ]; then
    echo "::error::EPL_PRICE_FEED_TOKEN is not set: nothing was written. The feed is never published to the public repository."
    return 1
  fi
  git push "$remote" "$1:refs/heads/${FEED_BRANCH}"
}
