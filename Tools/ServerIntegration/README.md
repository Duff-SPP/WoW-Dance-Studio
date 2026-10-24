# Persistent custom dance states

The tested CoA/AzerothCore server needs a source change in
`src/server/game/Handlers/ChatHandler.cpp`. Its original text-emote handler retains
only the stock dance as a persistent state and dispatches custom dances as
one-shot animations. The visible symptom is dancing stopping while music continues.

## Apply to your own server checkout

1. Review `persistent-dance-state.patch` against your server version. From the
   server source root, run `git apply --check /path/to/persistent-dance-state.patch`.
2. Apply with `git apply /path/to/persistent-dance-state.patch` only if compatible.
   Adapt the change if your core differs; do not force a failed patch.
3. Build and verify the worldserver using that core's supported workflow.
4. Deploy your rebuilt worldserver and matching server DBCs, then restart the realm.

The patch matches additional dance states against stock dance DBC metadata,
sets the persistent NPC emote state, and clears it on relevant stop/emote paths.
Other cores may already implement the required behavior. This is normally a
one-time core integration rather than a rebuild for each dance pack.

The patch retains AzerothCore's GPL-2.0-or-later context and copyright attribution;
see `../../THIRD_PARTY_NOTICES.md` and `../../LICENSES/GPL-2.0-or-later.txt`.
Client native compatibility remains a separate requirement.

## Validation

Test the rebuilt server with the real client and matching pack. Cover stock dance,
custom persistent dance, Stop, movement/jumping, casting, combat, another emote,
death, and optional one-shot playback. No server binary or private acceptance
report is distributed, and the source-only package makes no universal gameplay
compatibility claim.

The optional `../server_dance_state_regression.py --core <server-checkout>` helper
extracts source cases from a compatible patched checkout and compares against
its `git show HEAD:` baseline. It requires Git and a C++20 compiler. It depends on
the tested core's source structure and is not a general cross-core test suite.
