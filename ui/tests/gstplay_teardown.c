/* Actual GstPlay worker teardown with GTK-shaped signal-adapter ownership.
 * No GTK/display, audio device or model. NOT evidence of GTK teardown safety.
 * cc -g -O1 -fsanitize=address,undefined ui/tests/gstplay_teardown.c \
 *   $(pkg-config --cflags --libs gstreamer-play-1.0) -o WORKSPACE/gstplay-teardown
 * Usage: gstplay-teardown ABSOLUTE_SYNTHETIC_SILENT_MP4 CYCLES (1..4)
 * Set TMPDIR to a private Workspace evidence directory for the error fixture.
 */
#include <gst/play/play.h>
#include <glib/gstdio.h>
#include <stdlib.h>

typedef struct {
    GstPlay *play;
    GstClockTime position;
    guint infos, seeks;
    gboolean error;
} Probe;
static void gone(gpointer data, GObject *object) { (void)object; *(gboolean *)data = TRUE; }
static void position_updated(GstPlaySignalAdapter *adapter, GstClockTime position, Probe *probe) {
    (void)adapter; probe->position = position;
    GstPlayMediaInfo *info = gst_play_get_media_info(probe->play); /* full-owned COPY */
    if (info) g_object_unref(info);
}
static void media_updated(GstPlaySignalAdapter *adapter, GstPlayMediaInfo *borrowed, Probe *probe) {
    (void)adapter;
    g_assert_true(GST_IS_PLAY_MEDIA_INFO(borrowed)); /* signal arg is borrowed */
    GstPlayMediaInfo *copy = gst_play_get_media_info(probe->play);
    if (copy) { probe->infos++; g_object_unref(copy); }
}
static void seek_done(GstPlaySignalAdapter *adapter, GstClockTime position, Probe *probe) {
    (void)adapter; probe->position = position; probe->seeks++;
}
static void play_error(GstPlaySignalAdapter *adapter, GError *error, GstStructure *details, Probe *probe) {
    (void)adapter; (void)details; g_assert_nonnull(error); probe->error = TRUE;
}
static void wait_for(Probe *probe, gboolean error, gboolean seek) {
    gint64 deadline = g_get_monotonic_time() + 5000000;
    while (g_get_monotonic_time() < deadline) {
        while (g_main_context_iteration(NULL, FALSE));
        if (error ? probe->error : (!probe->error &&
                (seek ? probe->seeks > 0 : probe->position >= 250 * GST_MSECOND))) return;
        if (probe->error && !error) g_error("unexpected actual playback failure");
        g_usleep(1000); /* cadence only; readiness always observed */
    }
    g_error("actual GstPlay state timed out");
}
int main(int argc, char **argv) {
    gst_init(&argc, &argv);
    if (argc != 3 || !g_path_is_absolute(argv[1])) return 2;
    char *end = NULL;
    long cycles = strtol(argv[2], &end, 10);
    if (!end || *end || cycles < 1 || cycles > 4) return 2;
    char *uri = gst_filename_to_uri(argv[1], NULL);
    g_assert_nonnull(uri);
    char *directory = g_dir_make_tmp("gstplay-error-XXXXXX", NULL);
    g_assert_nonnull(directory);
    char *path = g_build_filename(directory, "invalid.mp4", NULL);
    g_assert_true(g_file_set_contents(path, "not a media container", -1, NULL));
    char *error_uri = gst_filename_to_uri(path, NULL);
    const char *scenarios[] = {"play-replay", "playing-remove", "prepare-cancel", "decode-error"};
    for (long i = 0; i < cycles; i++) for (guint scenario = 0; scenario < G_N_ELEMENTS(scenarios); scenario++) {
        Probe probe = {.play = gst_play_new(NULL)}; /* owns worker until final unref */
        gboolean finalized = FALSE;
        g_object_weak_ref(G_OBJECT(probe.play), gone, &finalized);
        GstElement *pipeline = gst_play_get_pipeline(probe.play); /* transfer full */
        GstElement *video = gst_element_factory_make("fakesink", NULL);
        GstElement *audio = gst_element_factory_make("fakesink", NULL);
        g_assert_nonnull(video); g_assert_nonnull(audio);
        g_object_set(video, "sync", TRUE, NULL);
        g_object_set(pipeline, "video-sink", video, "audio-sink", audio, NULL);
        GstPlaySignalAdapter *adapter = gst_play_signal_adapter_new(probe.play); /* full */
        g_signal_connect(adapter, "position-updated", G_CALLBACK(position_updated), &probe);
        g_signal_connect(adapter, "media-info-updated", G_CALLBACK(media_updated), &probe);
        g_signal_connect(adapter, "seek-done", G_CALLBACK(seek_done), &probe);
        g_signal_connect(adapter, "error", G_CALLBACK(play_error), &probe);
        gst_play_set_uri(probe.play, scenario == 3 ? error_uri : uri);
        if (scenario == 2) gst_play_pause(probe.play); /* cancel during preparation */
        else {
            gst_play_play(probe.play);
            wait_for(&probe, scenario == 3, FALSE);
            if (scenario == 0) {
                g_assert_cmpuint(probe.infos, >, 0);
                gst_play_pause(probe.play);
                gst_play_seek(probe.play, 0);
                wait_for(&probe, FALSE, TRUE);
                g_assert_cmpuint(probe.position, ==, 0);
                gst_play_play(probe.play);
                wait_for(&probe, FALSE, FALSE);
            }
        }
        /* GTK order: disconnect callbacks, unref adapter, stop and unref play,
         * then release the separately full-owned pipeline. No deferred unref. */
        g_signal_handlers_disconnect_by_data(adapter, &probe);
        g_object_unref(adapter);
        gst_play_stop(probe.play);
        gst_object_unref(probe.play); /* worker joins, including media_info unref */
        gst_object_unref(pipeline);
        g_assert_true(finalized);
        while (g_main_context_iteration(NULL, FALSE));
        g_print("cycle %ld %s: adapter disconnect/stop/join/finalize complete\n", i + 1, scenarios[scenario]);
    }
    g_free(uri); g_free(error_uri);
    g_assert_cmpint(g_unlink(path), ==, 0); g_assert_cmpint(g_rmdir(directory), ==, 0);
    g_free(path); g_free(directory);
    gst_deinit();
    return 0;
}
