#include "video_review_gate.h"

static void seek_is_not_playback(void) {
    VideoReviewGate gate = {0};
    video_review_position(&gate, 0, 1000000); /* prepared, paused */
    video_review_state(&gate, FALSE, TRUE);
    video_review_state(&gate, FALSE, FALSE);
    video_review_position(&gate, 500000, 1500000);
    video_review_position(&gate, 1000000, 2000000);
    g_assert_false(gate.played);
    video_review_state(&gate, TRUE, FALSE);
    video_review_position(&gate, 1000000, 3000000); /* baseline only */
    g_assert_false(gate.played);
    video_review_state(&gate, TRUE, TRUE); /* seek during playback */
    video_review_state(&gate, TRUE, FALSE);
    video_review_position(&gate, 2000000, 3250000);
    g_assert_false(gate.played); /* completion is not playback */
    video_review_position(&gate, 2250000, 3500000);
    g_assert_true(gate.played);
}
static void discontinuity_pause_and_reset(void) {
    VideoReviewGate gate = {0};
    video_review_state(&gate, TRUE, FALSE);
    video_review_position(&gate, 0, 1000000);
    video_review_position(&gate, 3000000, 1250000); /* unexplained jump */
    g_assert_false(gate.played);
    video_review_state(&gate, FALSE, FALSE);
    video_review_position(&gate, 3500000, 2000000);
    video_review_state(&gate, TRUE, FALSE);
    video_review_position(&gate, 3500000, 2250000);
    g_assert_false(gate.played);
    video_review_position(&gate, 3750000, 2500000);
    g_assert_true(gate.played);
    gate = (VideoReviewGate){0}; /* remove/hide/error/new attachment */
    g_assert_false(gate.played);
    video_review_state(&gate, TRUE, FALSE);
    video_review_position(&gate, 1000000, 3000000);
    video_review_position(&gate, 0, 3250000); /* replay resets baseline */
    g_assert_false(gate.played);
    video_review_position(&gate, 250000, 3500000);
    g_assert_true(gate.played);
}
static void frequent_updates_and_invalid_clock(void) {
    VideoReviewGate gate = {0};
    video_review_state(&gate, TRUE, FALSE);
    video_review_position(&gate, 0, 1000000);
    for (int i = 1; i < 10; i++) {
        video_review_position(&gate, i * 10000, 1000000 + i * 10000);
        g_assert_false(gate.played);
    }
    video_review_position(&gate, 100000, 1100000);
    g_assert_true(gate.played); /* frequent updates accumulate actual advance */
    gate = (VideoReviewGate){0};
    video_review_state(&gate, TRUE, FALSE);
    video_review_position(&gate, 0, 1000000);
    video_review_position(&gate, 500000, 1000000); /* no monotonic advance */
    g_assert_false(gate.played);
    video_review_position(&gate, 1000000, 3000000); /* long observation gap */
    g_assert_false(gate.played);
}
int main(int argc, char **argv) {
    g_test_init(&argc, &argv, NULL);
    g_test_add_func("/video-review/seek-not-playback", seek_is_not_playback);
    g_test_add_func("/video-review/discontinuity-pause-reset", discontinuity_pause_and_reset);
    g_test_add_func("/video-review/frequent-updates-invalid-clock", frequent_updates_and_invalid_clock);
    return g_test_run();
}
