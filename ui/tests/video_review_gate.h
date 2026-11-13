/* Quarantined review policy shared ONLY by the deterministic test and GTK
 * diagnosis probe. Not linked into the UI and not a video activation gate.
 * Records playback eligibility only, NEVER user review or Send consent.
 * Call state on playing/seeking notifications; position ONLY on timestamp
 * notifications, with g_get_monotonic_time(). Every seek invalidates baseline.
 */
#ifndef VIDEO_REVIEW_GATE_H
#define VIDEO_REVIEW_GATE_H
#include <glib.h>

typedef struct {
    gboolean playing, seeking, baseline, played;
    gint64 position, time;
} VideoReviewGate;

static void video_review_state(VideoReviewGate *gate, gboolean playing, gboolean seeking) {
    if (playing != gate->playing || seeking != gate->seeking) gate->baseline = FALSE;
    gate->playing = playing;
    gate->seeking = seeking;
}
static void video_review_position(VideoReviewGate *gate, gint64 position, gint64 now) {
    if (!gate->playing || gate->seeking) { gate->baseline = FALSE; return; }
    gint64 elapsed = now - gate->time, advanced = position - gate->position;
    /* A positive timestamp or forward discontinuity is not playback proof.
     * Require >=100ms of plausible advance between steady playback samples.
     * The 50ms allowance accommodates notification jitter, not seek jumps.
     */
    if (gate->baseline && elapsed > 0 && elapsed <= 1000000 &&
            advanced >= 0 && advanced <= elapsed + 50000) {
        if (elapsed >= 100000 && advanced >= 100000) gate->played = TRUE;
        return; /* accumulate frequent timestamp updates from the baseline */
    }
    gate->position = position;
    gate->time = now;
    gate->baseline = TRUE;
}
#endif
