/* Standalone diagnosis, NOT the application or an enabled video path.
 * cc -g -O1 -fsanitize=address,undefined ui/tests/gtk_media_teardown.c \
 *   $(pkg-config --cflags --libs gtk4) -o WORKSPACE/gtk-media-teardown
 * Parent must coordinate the machine lease BEFORE permitting this window.
 * HYPRNEURO_GTK_VIDEO_PROBE=1 HYPRNEURO_TEST_SESSION=SESSION \
 *   gtk-media-teardown ABSOLUTE_SYNTHETIC_MP4 CYCLES picture|video
 * Compare the original GtkPicture and GtkVideo with identical owning refs.
 */
#include <gtk/gtk.h>
#include <stdlib.h>
#include <sys/wait.h>
#include <unistd.h>
#include "video_review_gate.h"

static gboolean finalized;
static const char *session;
static void safe(void) {
    char *output = NULL;
    int status;
    char *args[] = {"/usr/bin/loginctl", "show-session", (char *)session,
        "-p", "User", "-p", "Remote", "-p", "Type", "-p", "Active", "-p", "LockedHint", NULL};
    g_assert_true(g_spawn_sync(NULL, args, NULL, 0, NULL, NULL, &output, NULL, &status, NULL));
    g_assert_true(WIFEXITED(status) && WEXITSTATUS(status) == 0);
    char *expected = g_strdup_printf("User=%u", (unsigned)getuid());
    char **lines = g_strsplit(output, "\n", -1);
    const char *values[] = {expected, "Remote=no", "Type=wayland", "Active=yes", "LockedHint=no"};
    for (guint i = 0; i < G_N_ELEMENTS(values); i++) g_assert_true(g_strv_contains((const char *const *)lines, values[i]));
    g_strfreev(lines); g_free(expected); g_free(output);
    char *locker[] = {"/usr/bin/pgrep", "-x", "hyprlock|swaylock|waylock|gtklock", NULL};
    g_assert_true(g_spawn_sync(NULL, locker, NULL, 0, NULL, NULL, NULL, NULL, &status, NULL));
    g_assert_true(WIFEXITED(status) && WEXITSTATUS(status) == 1);
}
static void events(void) {
    static gint64 last_check;
    if (g_get_monotonic_time() - last_check >= 100000) {
        safe(); last_check = g_get_monotonic_time();
    }
    while (g_main_context_iteration(NULL, FALSE));
}
static void gone(gpointer data, GObject *object) { (void)data; (void)object; finalized = TRUE; }
static void changed(GObject *object, GParamSpec *spec, gpointer data) {
    GtkMediaStream *stream = GTK_MEDIA_STREAM(object);
    VideoReviewGate *gate = data;
    video_review_state(gate, gtk_media_stream_get_playing(stream), gtk_media_stream_is_seeking(stream));
    if (!g_strcmp0(spec->name, "timestamp"))
        video_review_position(gate, gtk_media_stream_get_timestamp(stream), g_get_monotonic_time());
}
/* All waits observe actual state; sleep is only the polling cadence. */
static void wait_for(GtkMediaStream *stream, gboolean error, gint64 position) {
    gint64 deadline = g_get_monotonic_time() + 5000000;
    while (g_get_monotonic_time() < deadline) {
        events();
        if (error) { if (gtk_media_stream_get_error(stream)) return; }
        else {
            const GError *failure = gtk_media_stream_get_error(stream);
            if (failure) g_error("decoder: %s", failure->message);
            if (gtk_media_stream_is_prepared(stream) && !gtk_media_stream_is_seeking(stream) &&
                    gtk_media_stream_get_timestamp(stream) >= position) return;
        }
        g_usleep(1000);
    }
    g_error("actual decoder state timed out");
}
int main(int argc, char **argv) {
    if (g_strcmp0(g_getenv("HYPRNEURO_GTK_VIDEO_PROBE"), "1")) return 77;
    session = g_getenv("HYPRNEURO_TEST_SESSION");
    if (!session || !*session || argc != 4 || !g_path_is_absolute(argv[1])) return 2;
    char *end = NULL;
    long cycles = strtol(argv[2], &end, 10);
    if (!end || *end || cycles < 1 || cycles > 4 ||
        (g_strcmp0(argv[3], "picture") && g_strcmp0(argv[3], "video"))) return 2;
    safe(); /* independently verify fresh unlock BEFORE gtk_init or a window */
    gtk_init();
    gboolean video = !g_strcmp0(argv[3], "video");
    GFile *file = g_file_new_for_path(argv[1]);
    GFileInputStream *input_file = g_file_read(file, NULL, NULL);
    g_assert_nonnull(input_file);
    GBytes *bytes = g_input_stream_read_bytes(G_INPUT_STREAM(input_file), 3 * 1024 * 1024 + 1, NULL, NULL);
    g_assert_nonnull(bytes);
    g_assert_cmpuint(g_bytes_get_size(bytes), >, 0);
    g_assert_cmpuint(g_bytes_get_size(bytes), <=, 3 * 1024 * 1024);
    g_object_unref(input_file); g_object_unref(file);
    const char *scenarios[] = {"play-replay-remove", "playing-hide", "prepare-cancel", "decode-error"};
    for (long i = 0; i < cycles; i++) for (guint scenario = 0; scenario < G_N_ELEMENTS(scenarios); scenario++) {
        safe();
        GtkMediaStream *stream = gtk_media_file_new(); /* application owns ref */
        finalized = FALSE; g_object_weak_ref(G_OBJECT(stream), gone, NULL);
        VideoReviewGate gate = {0};
        g_signal_connect(stream, "notify", G_CALLBACK(changed), &gate);
        gtk_media_stream_set_muted(stream, TRUE);
        GtkWidget *window = gtk_window_new();
        GtkWidget *widget = video ? gtk_video_new_for_media_stream(stream) :
            gtk_picture_new_for_paintable(GDK_PAINTABLE(stream)); /* widget owns ref */
        if (video) {
            gtk_video_set_autoplay(GTK_VIDEO(widget), FALSE);
            gtk_video_set_loop(GTK_VIDEO(widget), FALSE);
        }
        gtk_window_set_title(GTK_WINDOW(window), "Hyprneuro synthetic teardown probe");
        gtk_window_set_default_size(GTK_WINDOW(window), 320, 180);
        gtk_window_set_child(GTK_WINDOW(window), widget);
        safe(); gtk_window_present(GTK_WINDOW(window));
        GBytes *content = scenario == 3 ? g_bytes_new_static("not a media container", 21) : g_bytes_ref(bytes);
        GInputStream *input = g_memory_input_stream_new_from_bytes(content);
        g_bytes_unref(content);
        gtk_media_file_set_input_stream(GTK_MEDIA_FILE(stream), input);
        g_object_unref(input); /* media file retains the immutable snapshot */
        if (scenario < 2) {
            wait_for(stream, FALSE, 0);
            g_assert_false(gtk_media_stream_get_playing(stream));
            g_assert_false(gate.played);
            safe(); gtk_media_stream_seek(stream, 500000);
            wait_for(stream, FALSE, 500000);
            g_assert_false(gtk_media_stream_get_playing(stream));
            g_assert_false(gate.played); /* paused seek must not unlock review */
            g_print("cycle %ld %s: paused seek, playback eligibility still false\n", i+1, scenarios[scenario]);
            safe(); gtk_media_stream_play(stream);
            wait_for(stream, FALSE, 1250000);
            g_assert_true(gate.played);
            if (scenario == 0) {
                safe(); gtk_media_stream_pause(stream);
                gtk_media_stream_seek(stream, 0);
                wait_for(stream, FALSE, 0);
                g_assert_cmpint(gtk_media_stream_get_timestamp(stream), ==, 0);
                safe(); gtk_media_stream_play(stream);
                wait_for(stream, FALSE, 500000);
                g_print("cycle %ld: actual play/replay advanced\n", i+1);
            } else { safe(); gtk_widget_set_visible(window, FALSE); }
        } else if (scenario == 3) {
            wait_for(stream, TRUE, 0);
            g_assert_false(gate.played);
            g_print("cycle %ld: actual decoder error observed\n", i+1);
        } /* scenario 2 clears an actual in-flight decoder before preparation */
        safe();
        g_signal_handlers_disconnect_by_data(stream, &gate);
        gtk_media_stream_pause(stream);
        if (video) gtk_video_set_media_stream(GTK_VIDEO(widget), NULL);
        else gtk_picture_set_paintable(GTK_PICTURE(widget), NULL);
        gtk_media_file_clear(GTK_MEDIA_FILE(stream)); /* joins GstPlay worker */
        g_object_unref(stream);
        g_assert_true(finalized); /* no retained/leaked application stream ref */
        gtk_window_destroy(GTK_WINDOW(window));
        events();
        g_print("cycle %ld %s %s: detach/clear/unref/destroy complete\n", i+1, argv[3], scenarios[scenario]);
    }
    g_bytes_unref(bytes);
    return 0;
}
