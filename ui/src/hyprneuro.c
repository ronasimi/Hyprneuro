/* Hyprneuro: transparent GTK4 layer-shell overlay, bottom-right.
 *
 * A component of the Hyprneuro assistant. Talks to the Hyprneuro sidecar
 * over its Unix socket for monitoring, agent_chat (streaming), and ui_status.
 *
 * Architecture:
 *  - Chat streaming runs in a GTask worker thread; UI updates are posted
 *    to the main thread via g_main_context_invoke().
 *  - Monitoring polls use a standalone connection (no shared socket state).
 *  - Settings view is a GtkStack page within the same window.
 *  - File picker uses GtkFileChooserNative (portal-backed on Wayland).
 *  - History nodes use json_node_ref() for correct ownership.
 *
 * Layer-shell: TOP layer, anchored bottom+right, 9px margin, exclusive_zone 0.
 */
#include <gtk/gtk.h>
#include <gtk4-layer-shell/gtk4-layer-shell.h>
#include <json-glib/json-glib.h>
#include <glib-unix.h>
#include <gio/gunixsocketaddress.h>
#include <gst/gst.h>
#include <gst/app/gstappsink.h>
#include <gst/video/video.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <errno.h>

#define MARGIN_PX 9
#define DEFAULT_WIDTH 656
#define MONITOR_POLL_MS 2000
#define MAX_HISTORY 20
#define DEFAULT_MAX_TOKENS 4096

typedef enum { SIZE_COMPACT, SIZE_RESTORE, SIZE_FULL } TranscriptSize;

/* ---- forward declarations for callback data ------------------------------ */
typedef struct App App;

typedef struct {
    App *app;
    char *text;
} DeltaData;

typedef struct {
    App *app;
    gboolean success;
    char *error;
} ChatDoneData;

typedef struct {
    char *sock_path;
    char *message;
    char *history_json;
    char *media_b64;   /* base64-encoded file data, or NULL */
    char *media_mime;  /* MIME type, or NULL */
    App *app;
} ChatTaskData;

/* ---- App ----------------------------------------------------------------- */
struct App {
    GtkWindow *win;
    GtkWidget *panel;
    GtkStack *stack;
    GtkWidget *chat_page;
    GtkWidget *settings_page;
    GtkWidget *settings_scroll;

    GtkWidget *transcript, *scroller, *composer;
    GtkTextView *input;
    GtkWidget *send, *size_toggle, *attach_btn, *audio_btn, *vision_btn, *settings_btn;
    GtkWidget *attach_strip;

    GtkWidget *status, *metrics;

    char *sidecar_sock;
    char *control_sock;
    GSocketService *svc;

    GMainLoop *loop;
    TranscriptSize size;
    gboolean shown, busy;
    GPtrArray *history;
    guint monitor_timer;
    gboolean user_scrolled_up;

    GtkTextTag *tag_user, *tag_asst;

    GString *current_answer;
    char *current_msg;

    GPtrArray *attachments;

    /* Media preview area. */
    GtkWidget *media_preview;
    GtkWidget *camera_picture;
    GtkWidget *media_controls;
    GtkWidget *media_label;

    /* GStreamer camera pipeline. */
    GstElement *camera_pipe;
    GstElement *camera_sink;
    gboolean    camera_active;
    char       *captured_file;
    guint8     *frame_bgr;
    int         frame_w, frame_h, frame_stride;

    /* Audio recording state. */
    GstElement *audio_pipe;
    GstElement *audio_sink;
    gboolean     audio_recording;
    guint        audio_timer;
    int          audio_seconds;
    gdouble      audio_rms;
    GtkWidget   *audio_level;
    GtkWidget   *audio_timer_lbl;
    char        *recorded_file;
};

/* ---- utility ------------------------------------------------------------- */
static JsonNode *jmember(JsonNode *node, const char *key) {
    if (!node || !JSON_NODE_HOLDS_OBJECT(node)) return NULL;
    return json_object_get_member(json_node_get_object(node), key);
}

static double jnum(JsonNode *n, double def) {
    if (!n) return def;
    JsonNodeType t = json_node_get_node_type(n);
    if (t == G_TYPE_DOUBLE) return json_node_get_double(n);
    if (t == G_TYPE_INT) return (double)json_node_get_int(n);
    return def;
}

static void set_status(App *a, const char *text) {
    gtk_label_set_text(GTK_LABEL(a->status), text);
}

/* ---- transcript ---------------------------------------------------------- */
static void transcript_scroll_to_bottom(App *a) {
    if (a->user_scrolled_up) return;
    GtkAdjustment *adj = gtk_scrolled_window_get_vadjustment(GTK_SCROLLED_WINDOW(a->scroller));
    if (adj)
        gtk_adjustment_set_value(adj, gtk_adjustment_get_upper(adj));
}

static void transcript_append(App *a, const char *who, const char *text) {
    GtkTextBuffer *buf = gtk_text_view_get_buffer(GTK_TEXT_VIEW(a->transcript));
    GtkTextIter end;
    gtk_text_buffer_get_end_iter(buf, &end);
    const char *tag_name = (who[0] == 'y') ? "user" : "asst";
    char *styled = g_strdup_printf("\n%s: %s\n", who, text);
    gtk_text_buffer_insert_with_tags_by_name(buf, &end, styled, -1, tag_name, NULL);
    g_free(styled);
    transcript_scroll_to_bottom(a);
}

static void on_scroll_adjustment(App *a, GtkAdjustment *adj) {
    double upper = gtk_adjustment_get_upper(adj);
    double val = gtk_adjustment_get_value(adj);
    double page = gtk_adjustment_get_page_size(adj);
    a->user_scrolled_up = (upper - (val + page)) > 8.0;
}

static void apply_transcript_size(App *a) {
    switch (a->size) {
        case SIZE_COMPACT:
            gtk_widget_set_visible(a->scroller, FALSE);
            break;
        case SIZE_RESTORE:
            gtk_widget_set_visible(a->scroller, TRUE);
            gtk_widget_set_size_request(a->scroller, DEFAULT_WIDTH, DEFAULT_WIDTH / 2);
            break;
        case SIZE_FULL:
            gtk_widget_set_visible(a->scroller, TRUE);
            gtk_widget_set_size_request(a->scroller, DEFAULT_WIDTH, DEFAULT_WIDTH);
            break;
    }
}

/* ---- history ------------------------------------------------------------- */
static void push_history(App *a, const char *role, const char *content) {
    if (a->history->len >= MAX_HISTORY)
        g_ptr_array_remove_index(a->history, 0); /* free func handles it */
    JsonBuilder *hb = json_builder_new();
    json_builder_begin_object(hb);
    json_builder_set_member_name(hb, "role");
    json_builder_add_string_value(hb, role);
    json_builder_set_member_name(hb, "content");
    json_builder_add_string_value(hb, content);
    json_builder_end_object(hb);
    /* json_node_ref takes an ownership reference so the node survives
     * after the builder is freed. This fixes the use-after-free that
     * crashed on the second prompt. */
    g_ptr_array_add(a->history, json_node_ref(json_builder_get_root(hb)));
    g_object_unref(hb);
}

static char *history_to_json(App *a) {
    JsonBuilder *b = json_builder_new();
    json_builder_begin_array(b);
    for (guint i = 0; i < a->history->len; i++) {
        JsonNode *node = *(JsonNode **)g_ptr_array_index(a->history, i);
        json_builder_add_value(b, node);
    }
    json_builder_end_array(b);
    JsonGenerator *g = json_generator_new();
    json_generator_set_root(g, json_builder_get_root(b));
    char *json = json_generator_to_data(g, NULL);
    g_object_unref(g);
    g_object_unref(b);
    return json;
}

/* ---- sidecar IPC (standalone connection per call) ------------------------ */
/* Connect, send one JSON line, read one JSON line response, return "result"
 * as a JSON string (caller g_free's) or NULL on error. */
static char *sidecar_call(const char *sock_path, const char *action, GError **err) {
    GSocketClient *client = g_socket_client_new();
    g_socket_client_set_timeout(client, 5);
    GSocketAddress *addr = g_unix_socket_address_new(sock_path);
    GSocketConnection *c = g_socket_client_connect(
        client, G_SOCKET_CONNECTABLE(addr), NULL, err);
    g_object_unref(addr);
    g_object_unref(client);
    if (!c) return NULL;

    JsonBuilder *b = json_builder_new();
    json_builder_begin_object(b);
    json_builder_set_member_name(b, "action");
    json_builder_add_string_value(b, action);
    json_builder_end_object(b);
    JsonGenerator *g = json_generator_new();
    json_generator_set_root(g, json_builder_get_root(b));
    char *req = json_generator_to_data(g, NULL);
    char *frame = g_strconcat(req, "\n", NULL);

    GOutputStream *out = g_io_stream_get_output_stream(G_IO_STREAM(c));
    gsize written;
    if (!g_output_stream_write_all(out, frame, strlen(frame), &written, NULL, err)) {
        g_object_unref(c);
        g_free(frame); g_free(req);
        g_object_unref(g); g_object_unref(b);
        return NULL;
    }
    g_free(frame); g_free(req);

    GDataInputStream *stream = g_data_input_stream_new(
        g_io_stream_get_input_stream(G_IO_STREAM(c)));
    char *resp = g_data_input_stream_read_line(stream, NULL, NULL, NULL);
    g_object_unref(stream);

    char *result_str = NULL;
    if (resp) {
        JsonParser *p = json_parser_new();
        if (json_parser_load_from_data(p, resp, -1, NULL)) {
            JsonNode *r = json_parser_get_root(p);
            if (jmember(r, "ok") && json_node_get_boolean(jmember(r, "ok"))) {
                JsonNode *res = jmember(r, "result");
                if (res) {
                    JsonGenerator *rg = json_generator_new();
                    json_generator_set_root(rg, res);
                    result_str = json_generator_to_data(rg, NULL);
                    g_object_unref(rg);
                }
            } else if (jmember(r, "error")) {
                g_set_error(err, G_IO_ERROR, G_IO_ERROR_FAILED,
                            "%s", json_node_get_string(jmember(r, "error")));
            }
        }
        g_object_unref(p);
        g_free(resp);
    }
    g_object_unref(c);
    g_object_unref(g);
    g_object_unref(b);
    return result_str;
}

/* ---- chat streaming (GTask worker thread) -------------------------------- */
/* These callbacks run in the MAIN thread (posted via g_main_context_invoke). */

static void on_delta(gpointer data) {
    DeltaData *d = data;
    App *a = d->app;
    g_string_append(a->current_answer, d->text);
    GtkTextBuffer *buf = gtk_text_view_get_buffer(GTK_TEXT_VIEW(a->transcript));
    GtkTextIter end;
    gtk_text_buffer_get_end_iter(buf, &end);
    gtk_text_buffer_insert_with_tags_by_name(buf, &end, d->text, -1, "asst", NULL);
    transcript_scroll_to_bottom(a);
    g_free(d->text);
    g_free(d);
}

static void on_chat_done(gpointer data) {
    ChatDoneData *d = data;
    App *a = d->app;
    a->busy = FALSE;
    gtk_widget_set_sensitive(a->send, TRUE);

    if (d->success) {
        set_status(a, "Hyprneuro · Local");
        /* Append a trailing newline after the assistant response. */
        GtkTextBuffer *buf = gtk_text_view_get_buffer(GTK_TEXT_VIEW(a->transcript));
        GtkTextIter end;
        gtk_text_buffer_get_end_iter(buf, &end);
        gtk_text_buffer_insert(buf, &end, "\n", -1);
        transcript_scroll_to_bottom(a);
        /* Record the exchange in bounded history. */
        push_history(a, "user", a->current_msg);
        push_history(a, "assistant", a->current_answer->str);
    } else {
        set_status(a, "Hyprneuro · error");
        GtkTextBuffer *buf = gtk_text_view_get_buffer(GTK_TEXT_VIEW(a->transcript));
        GtkTextIter end;
        gtk_text_buffer_get_end_iter(buf, &end);
        char *errtext = g_strdup_printf("\n[error: %s]\n", d->error ? d->error : "unknown");
        gtk_text_buffer_insert(buf, &end, errtext, -1);
        g_free(errtext);
        transcript_scroll_to_bottom(a);
    }

    g_free(a->current_msg);
    a->current_msg = NULL;
    g_string_set_size(a->current_answer, 0);
    gtk_widget_grab_focus(GTK_WIDGET(a->input));
    g_free(d->error);
    g_free(d);
}

/* Worker thread: blocking socket I/O, posts UI updates to main thread. */
static void chat_worker(GTask *task, gpointer source, gpointer task_data,
                        GCancellable *canc) {
    (void)task; (void)source; (void)canc;
    ChatTaskData *d = task_data;
    App *a = d->app;

    /* Connect to sidecar. */
    int fd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
    if (fd < 0) {
        ChatDoneData *dd = g_new0(ChatDoneData, 1);
        dd->app = a; dd->success = FALSE;
        dd->error = g_strdup("socket() failed");
        g_main_context_invoke(NULL, (GSourceFunc)on_chat_done, dd);
        goto cleanup;
    }
    struct sockaddr_un addr = {0};
    addr.sun_family = AF_UNIX;
    g_strlcpy(addr.sun_path, d->sock_path, sizeof(addr.sun_path));
    if (connect(fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        ChatDoneData *dd = g_new0(ChatDoneData, 1);
        dd->app = a; dd->success = FALSE;
        dd->error = g_strdup_printf("connect: %s", strerror(errno));
        g_main_context_invoke(NULL, (GSourceFunc)on_chat_done, dd);
        close(fd);
        goto cleanup;
    }

    /* Build and send request. */
    JsonBuilder *b = json_builder_new();
    json_builder_begin_object(b);
    json_builder_set_member_name(b, "action");
    json_builder_add_string_value(b, "agent_chat");
    json_builder_set_member_name(b, "message");
    json_builder_add_string_value(b, d->message);
    json_builder_set_member_name(b, "max_tokens");
    json_builder_add_int_value(b, DEFAULT_MAX_TOKENS);
    /* Parse the pre-serialized history array and embed it. */
    if (d->history_json && d->history_json[0]) {
        JsonParser *hp = json_parser_new();
        if (json_parser_load_from_data(hp, d->history_json, -1, NULL)) {
            json_builder_set_member_name(b, "history");
            json_builder_add_value(b, json_parser_get_root(hp));
        }
        g_object_unref(hp);
    }
    /* Embed media (base64-encoded file) if present. */
    if (d->media_b64 && d->media_b64[0]) {
        json_builder_set_member_name(b, "media");
        json_builder_begin_object(b);
        json_builder_set_member_name(b, "data");
        json_builder_add_string_value(b, d->media_b64);
        json_builder_set_member_name(b, "mime");
        json_builder_add_string_value(b, d->media_mime ? d->media_mime : "image/png");
        json_builder_end_object(b);
    }
    json_builder_end_object(b);
    JsonGenerator *g = json_generator_new();
    json_generator_set_root(g, json_builder_get_root(b));
    char *req = json_generator_to_data(g, NULL);
    char *frame = g_strconcat(req, "\n", NULL);

    ssize_t w = write(fd, frame, strlen(frame));
    g_free(frame); g_free(req);
    g_object_unref(g); g_object_unref(b);
    if (w < 0) {
        ChatDoneData *dd = g_new0(ChatDoneData, 1);
        dd->app = a; dd->success = FALSE;
        dd->error = g_strdup("write failed");
        g_main_context_invoke(NULL, (GSourceFunc)on_chat_done, dd);
        close(fd);
        goto cleanup;
    }

    /* Read streaming lines. */
    GString *line_buf = g_string_new("");
    char rbuf[8192];
    gboolean done = FALSE;
    while (!done) {
        ssize_t n = read(fd, rbuf, sizeof(rbuf));
        if (n <= 0) break;
        for (ssize_t i = 0; i < n; i++) {
            char c = rbuf[i];
            if (c == '\n') {
                char *line = g_string_free(line_buf, FALSE);
                g_string_assign(line_buf, "");
                if (line[0]) {
                    JsonParser *p = json_parser_new();
                    if (json_parser_load_from_data(p, line, -1, NULL)) {
                        JsonNode *r = json_parser_get_root(p);
                        JsonNode *tn = jmember(r, "type");
                        const char *type = tn ? json_node_get_string(tn) : NULL;
                        if (type && !g_strcmp0(type, "delta")) {
                            JsonNode *dn = jmember(r, "text");
                            const char *txt = dn ? json_node_get_string(dn) : "";
                            DeltaData *dd = g_new0(DeltaData, 1);
                            dd->app = a;
                            dd->text = g_strdup(txt);
                            g_main_context_invoke(NULL, (GSourceFunc)on_delta, dd);
                        } else if (type && !g_strcmp0(type, "done")) {
                            ChatDoneData *cd = g_new0(ChatDoneData, 1);
                            cd->app = a; cd->success = TRUE;
                            g_main_context_invoke(NULL, (GSourceFunc)on_chat_done, cd);
                            done = TRUE;
                        } else if (type && !g_strcmp0(type, "error")) {
                            const char *em = jmember(r, "error") ?
                                json_node_get_string(jmember(r, "error")) : "error";
                            ChatDoneData *cd = g_new0(ChatDoneData, 1);
                            cd->app = a; cd->success = FALSE;
                            cd->error = g_strdup(em);
                            g_main_context_invoke(NULL, (GSourceFunc)on_chat_done, cd);
                            done = TRUE;
                        }
                    }
                    g_object_unref(p);
                }
                g_free(line);
            } else {
                g_string_append_c(line_buf, c);
            }
        }
    }
    close(fd);
    g_string_free(line_buf, TRUE);

    /* If we exited the read loop without a done/error frame, report it. */
    if (!done) {
        ChatDoneData *cd = g_new0(ChatDoneData, 1);
        cd->app = a; cd->success = FALSE;
        cd->error = g_strdup("connection closed before completion");
        g_main_context_invoke(NULL, (GSourceFunc)on_chat_done, cd);
    }

cleanup:
    g_free(d->sock_path);
    g_free(d->message);
    g_free(d->history_json);
    g_free(d->media_b64);
    g_free(d->media_mime);
    g_free(d);
}

static void send_message(App *a) {
    if (a->busy) return;
    GtkTextBuffer *buf = gtk_text_view_get_buffer(GTK_TEXT_VIEW(a->input));
    GtkTextIter s, e;
    gtk_text_buffer_get_bounds(buf, &s, &e);
    char *msg = gtk_text_buffer_get_text(buf, &s, &e, FALSE);
    if (!msg || !*msg) { g_free(msg); return; }
    gtk_text_buffer_set_text(buf, "", -1);
    transcript_append(a, "you", msg);

    a->busy = TRUE;
    gtk_widget_set_sensitive(a->send, FALSE);
    set_status(a, "Hyprneuro · thinking…");

    /* Start an assistant line in the transcript. */
    GtkTextBuffer *tbuf = gtk_text_view_get_buffer(GTK_TEXT_VIEW(a->transcript));
    GtkTextIter tend;
    gtk_text_buffer_get_end_iter(tbuf, &tend);
    gtk_text_buffer_insert_with_tags_by_name(tbuf, &tend, "\nassistant: ", -1, "asst", NULL);

    /* Prepare task data (freed by the worker). */
    a->current_msg = g_strdup(msg);
    g_string_set_size(a->current_answer, 0);

    ChatTaskData *td = g_new0(ChatTaskData, 1);
    td->app = a;
    td->sock_path = g_strdup(a->sidecar_sock);
    td->message = g_strdup(msg);
    td->history_json = history_to_json(a);

    /* If there are attachments, include the first one as media. */
    if (a->attachments->len > 0) {
        GFile *f = g_ptr_array_index(a->attachments, 0);
        char *path = g_file_get_path(f);
        GError *ferr = NULL;
        gsize len = 0;
        gchar *contents = NULL;
        if (g_file_get_contents(path, &contents, &len, &ferr) &&
            len > 0 && len < 5 * 1024 * 1024) {
            td->media_b64 = g_base64_encode(contents, len);
            /* Guess MIME from extension. */
            char *name = g_file_get_basename(f);
            char *dot = strrchr(name, '.');
            if (dot) {
                if (!g_strcmp0(dot+1, "png")) td->media_mime = g_strdup("image/png");
                else if (!g_strcmp0(dot+1, "jpg") || !g_strcmp0(dot+1, "jpeg"))
                    td->media_mime = g_strdup("image/jpeg");
                else if (!g_strcmp0(dot+1, "webp")) td->media_mime = g_strdup("image/webp");
                else if (!g_strcmp0(dot+1, "wav")) td->media_mime = g_strdup("audio/wav");
                else if (!g_strcmp0(dot+1, "mp3")) td->media_mime = g_strdup("audio/mpeg");
                else td->media_mime = g_strdup("application/octet-stream");
            } else {
                td->media_mime = g_strdup("application/octet-stream");
            }
            g_free(name);
        } else {
            if (ferr) g_clear_error(&ferr);
        }
        g_free(contents);
        g_free(path);
    }

    GTask *task = g_task_new(a, NULL, NULL, NULL);
    g_task_set_task_data(task, td, NULL); /* worker frees it */
    g_task_run_in_thread(task, chat_worker);
    g_object_unref(task);
    g_free(msg);
}

/* ---- monitoring poll (standalone connection) ----------------------------- */
static gboolean poll_monitoring(gpointer data) {
    App *a = data;
    GError *err = NULL;
    char *mon_data = sidecar_call(a->sidecar_sock, "monitoring", &err);
    if (mon_data) {
        JsonParser *p = json_parser_new();
        if (json_parser_load_from_data(p, mon_data, -1, NULL)) {
            JsonNode *root = json_parser_get_root(p);
            if (JSON_NODE_HOLDS_OBJECT(root)) {
                JsonObject *o = json_node_get_object(root);
                GString *s = g_string_new("");
                double cpu = jnum(json_object_get_member(o, "cpu_pct"), -1);
                if (cpu >= 0) g_string_append_printf(s, "cpu %d%%  ", (int)cpu);
                JsonNode *rn = json_object_get_member(o, "ram");
                double rpct = (rn && JSON_NODE_HOLDS_OBJECT(rn)) ?
                    jnum(json_object_get_member(json_node_get_object(rn), "pct"), -1) : -1;
                if (rpct >= 0) g_string_append_printf(s, "ram %d%%", (int)rpct);
                gtk_label_set_text(GTK_LABEL(a->metrics), s->str);
                g_string_free(s, TRUE);
            }
        }
        g_object_unref(p);
        g_free(mon_data);
    } else {
        gtk_label_set_text(GTK_LABEL(a->metrics), "sidecar offline");
        g_clear_error(&err);
    }
    return G_SOURCE_CONTINUE;
}

/* ---- settings view ------------------------------------------------------- */
static void add_settings_row(GtkListBox *list, const char *label, const char *value) {
    GtkWidget *row = gtk_list_box_row_new();
    GtkWidget *box = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 12);
    GtkWidget *lbl = gtk_label_new(label);
    gtk_widget_set_halign(lbl, GTK_ALIGN_START);
    gtk_widget_set_hexpand(lbl, TRUE);
    gtk_label_set_xalign(GTK_LABEL(lbl), 0.0);
    GtkWidget *val = gtk_label_new(value);
    gtk_label_set_xalign(GTK_LABEL(val), 1.0);
    gtk_widget_add_css_class(val, "dim-label");
    gtk_box_append(GTK_BOX(box), lbl);
    gtk_box_append(GTK_BOX(box), val);
    gtk_list_box_row_set_child(GTK_LIST_BOX_ROW(row), box);
    gtk_list_box_append(list, row);
}

static void add_settings_section(GtkWidget *parent, const char *title) {
    GtkWidget *lbl = gtk_label_new(title);
    gtk_widget_add_css_class(lbl, "hn-settings-title");
    gtk_label_set_xalign(GTK_LABEL(lbl), 0.0);
    gtk_widget_set_margin_top(lbl, 12);
    gtk_widget_set_margin_bottom(lbl, 4);
    gtk_box_append(GTK_BOX(parent), lbl);
}

static void populate_settings(App *a) {
    /* Clear existing content. */
    GtkWidget *child = gtk_scrolled_window_get_child(GTK_SCROLLED_WINDOW(a->settings_scroll));
    if (child) gtk_widget_unparent(child);

    GtkWidget *content = gtk_box_new(GTK_ORIENTATION_VERTICAL, 4);
    gtk_widget_set_margin_start(content, 12);
    gtk_widget_set_margin_end(content, 12);
    gtk_widget_set_margin_top(content, 8);
    gtk_widget_set_margin_bottom(content, 8);

    /* Models & Inference */
    add_settings_section(content, "Models & Inference");
    GtkWidget *model_list = gtk_list_box_new();
    gtk_widget_add_css_class(model_list, "hn-settings");
    char *ui_data = sidecar_call(a->sidecar_sock, "ui_status", NULL);
    if (ui_data) {
        JsonParser *p = json_parser_new();
        if (json_parser_load_from_data(p, ui_data, -1, NULL)) {
            JsonNode *root = json_parser_get_root(p);
            JsonNode *models = jmember(root, "models");
            if (models && JSON_NODE_HOLDS_OBJECT(models)) {
                JsonObject *mo = json_node_get_object(models);
                const char *roles[] = {"text", "omni"};
                for (unsigned ri = 0; ri < 2; ri++) {
                    JsonNode *hn = json_object_get_member(mo, roles[ri]);
                    const char *state = (hn && json_node_get_boolean(hn)) ? "healthy" : "unavailable";
                    char *label = g_strdup_printf("%s model", roles[ri]);
                    add_settings_row(GTK_LIST_BOX(model_list), label, state);
                    g_free(label);
                }
            }
            JsonNode *pid_n = jmember(root, "pid");
            if (pid_n) {
                char *pid_str = g_strdup_printf("%ld", (long)json_node_get_int(pid_n));
                add_settings_row(GTK_LIST_BOX(model_list), "Sidecar PID", pid_str);
                g_free(pid_str);
            }
        }
        g_object_unref(p);
        g_free(ui_data);
    } else {
        add_settings_row(GTK_LIST_BOX(model_list), "Sidecar", "unreachable");
    }
    gtk_box_append(GTK_BOX(content), model_list);

    /* Monitoring */
    add_settings_section(content, "Monitoring");
    GtkWidget *mon_list = gtk_list_box_new();
    gtk_widget_add_css_class(mon_list, "hn-settings");
    char *mon_data = sidecar_call(a->sidecar_sock, "monitoring", NULL);
    if (mon_data) {
        JsonParser *p = json_parser_new();
        if (json_parser_load_from_data(p, mon_data, -1, NULL)) {
            JsonNode *root = json_parser_get_root(p);
            if (JSON_NODE_HOLDS_OBJECT(root)) {
                JsonObject *o = json_node_get_object(root);
                double cpu = jnum(json_object_get_member(o, "cpu_pct"), -1);
                if (cpu >= 0) {
                    char *s = g_strdup_printf("%.1f%%", cpu);
                    add_settings_row(GTK_LIST_BOX(mon_list), "CPU", s);
                    g_free(s);
                }
                JsonNode *rn = json_object_get_member(o, "ram");
                if (rn && JSON_NODE_HOLDS_OBJECT(rn)) {
                    double pct = jnum(json_object_get_member(json_node_get_object(rn), "pct"), -1);
                    double total = jnum(json_object_get_member(json_node_get_object(rn), "total_mb"), -1);
                    if (pct >= 0 && total > 0) {
                        char *s = g_strdup_printf("%.1f%% of %.0f MB", pct, total);
                        add_settings_row(GTK_LIST_BOX(mon_list), "Memory", s);
                        g_free(s);
                    }
                }
                JsonNode *apps = json_object_get_member(o, "apps");
                if (apps && JSON_NODE_HOLDS_OBJECT(apps)) {
                    JsonNode *focused = json_object_get_member(json_node_get_object(apps), "focused");
                    if (focused && json_node_get_node_type(focused) == G_TYPE_STRING)
                        add_settings_row(GTK_LIST_BOX(mon_list), "Focused app",
                                         json_node_get_string(focused));
                }
            }
        }
        g_object_unref(p);
        g_free(mon_data);
    } else {
        add_settings_row(GTK_LIST_BOX(mon_list), "Status", "unavailable");
    }
    gtk_box_append(GTK_BOX(content), mon_list);

    /* Appearance */
    add_settings_section(content, "Appearance");
    GtkWidget *app_list = gtk_list_box_new();
    gtk_widget_add_css_class(app_list, "hn-settings");
    const char *size_str = (a->size == SIZE_COMPACT) ? "Compact" :
                           (a->size == SIZE_FULL) ? "Full" : "Restored";
    add_settings_row(GTK_LIST_BOX(app_list), "Transcript size", size_str);
    add_settings_row(GTK_LIST_BOX(app_list), "Autoscroll", a->user_scrolled_up ? "Paused" : "Active");
    gtk_box_append(GTK_BOX(content), app_list);

    /* Application */
    add_settings_section(content, "Application");
    GtkWidget *app_info = gtk_list_box_new();
    gtk_widget_add_css_class(app_info, "hn-settings");
    add_settings_row(GTK_LIST_BOX(app_info), "Version", "0.1.0 (GTK4 layer-shell)");
    add_settings_row(GTK_LIST_BOX(app_info), "UI service", "hyprneuro-ui.service");
    add_settings_row(GTK_LIST_BOX(app_info), "Sidecar service", "hyprneuro.service");
    add_settings_row(GTK_LIST_BOX(app_info), "Hotkey", "SUPER+ALT+H");
    gtk_box_append(GTK_BOX(content), app_info);

    gtk_scrolled_window_set_child(GTK_SCROLLED_WINDOW(a->settings_scroll), content);
}

static void on_settings_back(GtkButton *btn, gpointer data) {
    (void)btn;
    App *a = data;
    gtk_stack_set_visible_child_name(a->stack, "chat");
}

static void on_settings_open(GtkButton *btn, gpointer data) {
    (void)btn;
    App *a = data;
    populate_settings(a);
    gtk_stack_set_visible_child_name(a->stack, "settings");
}

/* ---- file picker (portal-backed via GtkFileDialog) ----------------------- */
static void on_file_dialog_open(GObject *obj, GAsyncResult *result, gpointer data) {
    (void)obj;
    App *a = data;
    GError *err = NULL;
    GListModel *files = gtk_file_dialog_open_multiple_finish(
        GTK_FILE_DIALOG(obj), result, &err);
    if (err || !files) {
        g_clear_error(&err);
        return; /* cancelled or error */
    }
    guint n = g_list_model_get_n_items(files);
    for (guint i = 0; i < n; i++) {
        GFile *f = g_list_model_get_item(files, i);
        g_ptr_array_add(a->attachments, f);
        char *name = g_file_get_basename(f);
        GtkWidget *item = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 4);
        gtk_widget_add_css_class(item, "hn-attach-item");
        GtkWidget *lbl = gtk_label_new(name);
        gtk_box_append(GTK_BOX(item), lbl);
        GtkWidget *rm = gtk_button_new_from_icon_name("window-close-symbolic");
        g_signal_connect_swapped(rm, "clicked",
                                 G_CALLBACK(gtk_widget_unparent), item);
        gtk_box_append(GTK_BOX(item), rm);
        gtk_box_append(GTK_BOX(a->attach_strip), item);
        g_free(name);
    }
    g_object_unref(files);
    gtk_widget_set_visible(a->attach_strip, a->attachments->len > 0);
}

static void on_attach(GtkButton *btn, gpointer data) {
    (void)btn;
    App *a = data;
    GtkFileDialog *dialog = gtk_file_dialog_new();
    gtk_file_dialog_set_title(dialog, "Select files");
    /* Default filter: all files. */
    GtkFileFilter *all = gtk_file_filter_new();
    gtk_file_filter_set_name(all, "All files");
    gtk_file_filter_add_pattern(all, "*");
    gtk_file_dialog_set_default_filter(dialog, all);
    g_object_unref(all);
    gtk_file_dialog_open_multiple(dialog, a->win, NULL,
                                  (GAsyncReadyCallback)on_file_dialog_open, a);
    g_object_unref(dialog);
}

/* ---- camera viewfinder (GStreamer/PipeWire) ------------------------------- */
typedef struct {
    App *app;
    guint8 *pixels;
    int width, height, stride;
} FrameData;

static void on_frame_ready(gpointer data) {
    FrameData *fd = data;
    App *a = fd->app;
    int w = fd->width, h = fd->height, s = fd->stride;
    if (a->frame_bgr) g_free(a->frame_bgr);
    a->frame_bgr = fd->pixels;
    a->frame_w = w; a->frame_h = h; a->frame_stride = s;
    fd->pixels = NULL;
    if (a->camera_picture) {
        size_t bgra_size = (size_t)w * h * 4;
        guint8 *bgra = g_malloc(bgra_size);
        for (int y = 0; y < h; y++) {
            const guint8 *src = a->frame_bgr + (size_t)y * s;
            guint8 *dst = bgra + (size_t)y * w * 4;
            for (int x = 0; x < w; x++) {
                dst[x*4+0] = src[x*3+0];
                dst[x*4+1] = src[x*3+1];
                dst[x*4+2] = src[x*3+2];
                dst[x*4+3] = 255;
            }
        }
        GdkPixbuf *pb = gdk_pixbuf_new_from_data(
            bgra, GDK_COLORSPACE_RGB, TRUE, 8,
            w, h, w * 4, NULL, NULL);
        GdkTexture *tex = gdk_texture_new_for_pixbuf(pb);
        g_object_unref(pb);
        g_free(bgra);
        if (tex) {
            gtk_picture_set_paintable(GTK_PICTURE(a->camera_picture),
                                      GDK_PAINTABLE(tex));
            g_object_unref(tex);
        }
    } else if (a->frame_bgr) {
        g_free(a->frame_bgr);
        a->frame_bgr = NULL;
    }
    g_free(fd);
}

static void on_appsink_new_sample(GstElement *sink, gpointer data) {
    (void)sink;
    App *a = data;
    GstSample *sample = gst_app_sink_pull_sample(GST_APP_SINK(sink));
    if (!sample) return;
    GstBuffer *buf = gst_sample_get_buffer(sample);
    if (buf) {
        GstMapInfo map;
        if (gst_buffer_map(buf, &map, GST_MAP_READ)) {
            GstCaps *caps = gst_sample_get_caps(sample);
            if (caps) {
                GstStructure *st = gst_caps_get_structure(caps, 0);
                int w = 0, h = 0;
                gst_structure_get_int(st, "width", &w);
                gst_structure_get_int(st, "height", &h);
                int stride = w * 3;
                size_t sz = (size_t)stride * h;
                if (map.size >= sz && w > 0 && h > 0) {
                    guint8 *copy = g_malloc(sz);
                    memcpy(copy, map.data, sz);
                    FrameData *fd = g_new0(FrameData, 1);
                    fd->app = a;
                    fd->pixels = copy;
                    fd->width = w;
                    fd->height = h;
                    fd->stride = stride;
                    g_main_context_invoke(NULL, (GSourceFunc)on_frame_ready, fd);
                }
                gst_caps_unref(caps);
            }
            gst_buffer_unmap(buf, &map);
        }
    }
    gst_sample_unref(sample);
}

static void camera_stop(App *a) {
    if (a->camera_pipe) {
        gst_element_set_state(a->camera_pipe, GST_STATE_NULL);
        g_object_unref(a->camera_pipe);
        a->camera_pipe = NULL;
        a->camera_sink = NULL;
    }
    a->camera_active = FALSE;
    if (a->frame_bgr) { g_free(a->frame_bgr); a->frame_bgr = NULL; }
    if (a->media_preview)
        gtk_widget_set_visible(a->media_preview, FALSE);
    if (a->camera_picture)
        gtk_picture_set_paintable(GTK_PICTURE(a->camera_picture), NULL);
}

static void camera_start(App *a) {
    if (a->camera_active) return;
    GstElement *pipeline = gst_parse_launch(
        "pipewiresrc ! videoscale ! videoconvert "
        "! video/x-raw,format=BGR,width=640,height=480,framerate=15/1 "
        "! appsink name=sink sync=false", NULL);
    if (!pipeline) {
        set_status(a, "Hyprneuro · camera init failed");
        return;
    }
    a->camera_sink = gst_bin_get_by_name(GST_BIN(pipeline), "sink");
    if (!a->camera_sink) {
        g_object_unref(pipeline);
        set_status(a, "Hyprneuro · camera sink not found");
        return;
    }
    g_signal_connect(a->camera_sink, "new-sample",
                     G_CALLBACK(on_appsink_new_sample), a);
    a->camera_pipe = pipeline;
    GstStateChangeReturn ret = gst_element_set_state(
        pipeline, GST_STATE_PLAYING);
    if (ret == GST_STATE_CHANGE_FAILURE) {
        g_object_unref(pipeline);
        a->camera_pipe = NULL;
        a->camera_sink = NULL;
        set_status(a, "Hyprneuro · camera start failed");
        return;
    }
    a->camera_active = TRUE;
    if (a->media_preview)
        gtk_widget_set_visible(a->media_preview, TRUE);
    if (a->media_label)
        gtk_label_set_text(GTK_LABEL(a->media_label), "Camera · live");
    set_status(a, "Hyprneuro · camera");
}

static void on_camera_capture(GtkButton *btn, gpointer data) {
    (void)btn;
    App *a = data;
    if (!a->frame_bgr || a->frame_w <= 0) return;
    int w = a->frame_w, h = a->frame_h, s = a->frame_stride;
    cairo_surface_t *surface = cairo_image_surface_create(CAIRO_FORMAT_ARGB32, w, h);
    cairo_surface_flush(surface);
    unsigned char *dst = cairo_image_surface_get_data(surface);
    int dst_s = cairo_image_surface_get_stride(surface);
    for (int y = 0; y < h; y++) {
        const guint8 *src = a->frame_bgr + (size_t)y * s;
        unsigned char *d = dst + (size_t)y * dst_s;
        for (int x = 0; x < w; x++) {
            d[x*4+0] = src[x*3+2];
            d[x*4+1] = src[x*3+1];
            d[x*4+2] = src[x*3+0];
            d[x*4+3] = 255;
        }
    }
    cairo_surface_mark_dirty(surface);
    char *path = g_strdup_printf("/tmp/hyprneuro-capture-%ld.png",
                                  (long)g_get_real_time() / 1000000);
    cairo_surface_write_to_png(surface, path);
    cairo_surface_destroy(surface);
    if (a->captured_file) g_free(a->captured_file);
    a->captured_file = path;
    GFile *f = g_file_new_for_path(path);
    g_ptr_array_add(a->attachments, f);
    char *name = g_file_get_basename(f);
    GtkWidget *item = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 4);
    gtk_widget_add_css_class(item, "hn-attach-item");
    gtk_box_append(GTK_BOX(item), gtk_label_new(name));
    GtkWidget *rm = gtk_button_new_from_icon_name("window-close-symbolic");
    g_signal_connect_swapped(rm, "clicked",
                             G_CALLBACK(gtk_widget_unparent), item);
    gtk_box_append(GTK_BOX(item), rm);
    gtk_box_append(GTK_BOX(a->attach_strip), item);
    g_free(name);
    gtk_widget_set_visible(a->attach_strip, TRUE);
    if (a->media_label)
        gtk_label_set_text(GTK_LABEL(a->media_label), "Captured · attached");
}

static void on_screen_capture(GtkButton *btn, gpointer data) {
    (void)btn;
    App *a = data;
    /* Use grim for portal-backed screen capture. */
    char *path = g_strdup_printf("/tmp/hyprneuro-screen-%ld.png",
                                  (long)g_get_real_time() / 1000000);
    char *cmd = g_strdup_printf("grim %s 2>/dev/null", path);
    if (g_spawn_command_line_sync(cmd, NULL, NULL, NULL, NULL) == 0) {
        GFile *f = g_file_new_for_path(path);
        g_ptr_array_add(a->attachments, f);
        char *name = g_file_get_basename(f);
        GtkWidget *item = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 4);
        gtk_widget_add_css_class(item, "hn-attach-item");
        gtk_box_append(GTK_BOX(item), gtk_label_new(name));
        GtkWidget *rm = gtk_button_new_from_icon_name("window-close-symbolic");
        g_signal_connect_swapped(rm, "clicked",
                                 G_CALLBACK(gtk_widget_unparent), item);
        gtk_box_append(GTK_BOX(item), rm);
        gtk_box_append(GTK_BOX(a->attach_strip), item);
        g_free(name);
        gtk_widget_set_visible(a->attach_strip, TRUE);
        if (a->media_label)
            gtk_label_set_text(GTK_LABEL(a->media_label), "Screen captured · attached");
    } else {
        if (a->media_label)
            gtk_label_set_text(GTK_LABEL(a->media_label), "Screen capture failed");
    }
    g_free(cmd);
    g_free(path);
}

static void on_camera_cancel(GtkButton *btn, gpointer data) {
    (void)btn;
    camera_stop(data);
}

static void on_vision(GtkButton *btn, gpointer data) {
    (void)btn;
    App *a = data;
    if (a->camera_active) camera_stop(a);
    else camera_start(a);
}

/* ---- audio capture (PipeWire via GStreamer) ------------------------------- */
static void on_audio_level_sample(GstElement *sink, gpointer data) {
    (void)sink;
    App *a = data;
    GstSample *sample = gst_app_sink_pull_sample(GST_APP_SINK(sink));
    if (!sample) return;
    GstBuffer *buf = gst_sample_get_buffer(sample);
    if (buf) {
        GstMapInfo map;
        if (gst_buffer_map(buf, &map, GST_MAP_READ)) {
            const gint16 *pcm = (const gint16 *)map.data;
            guint n = map.size / 2;
            gdouble sum = 0;
            for (guint i = 0; i < n; i++)
                sum += (gdouble)pcm[i] * pcm[i];
            a->audio_rms = sqrt(sum / (gdouble)n) / 32768.0;
            gst_buffer_unmap(buf, &map);
        }
    }
    gst_sample_unref(sample);
}

static gboolean audio_tick(gpointer data) {
    App *a = data;
    a->audio_seconds++;
    char buf[32];
    snprintf(buf, sizeof buf, "%d:%02d", a->audio_seconds / 60, a->audio_seconds % 60);
    if (a->audio_timer_lbl)
        gtk_label_set_text(GTK_LABEL(a->audio_timer_lbl), buf);
    if (a->audio_level)
        gtk_level_bar_set_value(GTK_LEVEL_BAR(a->audio_level), a->audio_rms);
    return G_SOURCE_CONTINUE;
}

static void audio_stop(App *a) {
    if (a->audio_pipe) {
        gst_element_set_state(GST_ELEMENT(a->audio_pipe), GST_STATE_NULL);
        g_object_unref(a->audio_pipe);
        a->audio_pipe = NULL;
        a->audio_sink = NULL;
    }
    if (a->audio_timer) {
        g_source_remove(a->audio_timer);
        a->audio_timer = 0;
    }
    a->audio_recording = FALSE;
    a->audio_seconds = 0;
    a->audio_rms = 0;
    if (a->media_preview)
        gtk_widget_set_visible(a->media_preview, FALSE);
    if (a->audio_level)
        gtk_level_bar_set_value(GTK_LEVEL_BAR(a->audio_level), 0);
}

static void audio_start(App *a) {
    if (a->audio_recording) return;
    GstElement *pipeline = gst_parse_launch(
        "pipewiresrc ! audioconvert ! audioresample "
        "! audio/x-raw,format=S16LE,channels=1,rate=16000 "
        "! appsink name=sink sync=false", NULL);
    if (!pipeline) {
        set_status(a, "Hyprneuro · audio init failed");
        return;
    }
    a->audio_sink = gst_bin_get_by_name(GST_BIN(pipeline), "sink");
    if (!a->audio_sink) {
        g_object_unref(pipeline);
        set_status(a, "Hyprneuro · audio sink not found");
        return;
    }
    g_signal_connect(a->audio_sink, "new-sample",
                     G_CALLBACK(on_audio_level_sample), a);
    a->audio_pipe = pipeline;
    GstStateChangeReturn ret = gst_element_set_state(
        GST_ELEMENT(pipeline), GST_STATE_PLAYING);
    if (ret == GST_STATE_CHANGE_FAILURE) {
        g_object_unref(pipeline);
        a->audio_pipe = NULL;
        a->audio_sink = NULL;
        set_status(a, "Hyprneuro · audio start failed");
        return;
    }
    a->audio_recording = TRUE;
    a->audio_seconds = 0;
    a->audio_rms = 0;
    a->audio_timer = g_timeout_add(1000, audio_tick, a);
    if (a->media_preview)
        gtk_widget_set_visible(a->media_preview, TRUE);
    if (a->audio_level)
        gtk_widget_set_visible(a->audio_level, TRUE);
    if (a->audio_timer_lbl)
        gtk_widget_set_visible(a->audio_timer_lbl, TRUE);
    if (a->media_label)
        gtk_label_set_text(GTK_LABEL(a->media_label), "Recording…");
    set_status(a, "Hyprneuro · recording");
}

static void on_audio_stop_btn(GtkButton *btn, gpointer data) {
    (void)btn;
    audio_stop(data);
}

static void on_audio(GtkButton *btn, gpointer data) {
    (void)btn;
    App *a = data;
    if (a->audio_recording) audio_stop(a);
    else audio_start(a);
}

/* ---- show / hide / toggle ------------------------------------------------ */
static void show_ui(App *a) {
    if (a->shown) return;
    a->shown = TRUE;
    gtk_window_present(a->win);
    gtk_layer_set_keyboard_mode(a->win, GTK_LAYER_SHELL_KEYBOARD_MODE_ON_DEMAND);
    gtk_widget_grab_focus(GTK_WIDGET(a->input));
}

static void hide_ui(App *a) {
    if (!a->shown) return;
    a->shown = FALSE;
    gtk_widget_set_visible(GTK_WIDGET(a->win), FALSE);
}

static void toggle_ui(App *a) { a->shown ? hide_ui(a) : show_ui(a); }

static gboolean on_key(GtkEventControllerKey *c, guint keyval, guint code,
                       GdkModifierType state, gpointer data) {
    (void)c; (void)code; (void)state;
    App *a = data;
    if (keyval == GDK_KEY_Escape) {
        /* If settings is showing, go back to chat first. */
        if (!g_strcmp0(gtk_stack_get_visible_child_name(a->stack), "settings"))
            gtk_stack_set_visible_child_name(a->stack, "chat");
        else
            hide_ui(a);
        return TRUE;
    }
    return FALSE;
}

/* ---- control socket (ui.sock) -------------------------------------------- */
static void on_control_connect(GSocketService *svc, GSocketConnection *conn,
                               GObject *source, gpointer data) {
    (void)svc; (void)source;
    App *a = data;
    GDataInputStream *in = g_data_input_stream_new(
        g_io_stream_get_input_stream(G_IO_STREAM(conn)));
    char *line = g_data_input_stream_read_line(in, NULL, NULL, NULL);
    g_object_unref(in);
    if (line) {
        if (!g_strcmp0(line, "toggle")) toggle_ui(a);
        else if (!g_strcmp0(line, "show")) show_ui(a);
        else if (!g_strcmp0(line, "hide")) hide_ui(a);
        g_free(line);
    }
    g_object_unref(conn);
}

/* ---- size toggle --------------------------------------------------------- */
static void on_size_toggle(GtkButton *btn, gpointer data) {
    App *a = data;
    a->size = (a->size == SIZE_FULL) ? SIZE_COMPACT : SIZE_FULL;
    apply_transcript_size(a);
    gtk_button_set_icon_name(btn,
        a->size == SIZE_FULL ? "go-down-symbolic" : "go-up-symbolic");
}

/* ---- builder helper ------------------------------------------------------ */
static GtkWidget *circular(GtkWidget *box, const char *icon, GCallback cb,
                           App *a, const char *tip) {
    GtkWidget *btn = gtk_button_new_from_icon_name(icon);
    gtk_widget_add_css_class(btn, "jeevus-input-action");
    gtk_widget_set_valign(btn, GTK_ALIGN_CENTER);
    if (tip) gtk_widget_set_tooltip_text(btn, tip);
    g_signal_connect(btn, "clicked", cb, a);
    gtk_box_append(GTK_BOX(box), btn);
    return btn;
}

/* ---- signal callbacks (must match GTK signatures) ------------------------- */
static void on_send_clicked(GtkButton *btn, gpointer data) {
    (void)btn;
    send_message(data);
}

/* ---- main ---------------------------------------------------------------- */
int main(int argc, char **argv) {
    (void)argc; (void)argv;
    gtk_init();
    App *a = g_new0(App, 1);
    a->size = SIZE_RESTORE;
    a->history = g_ptr_array_new_with_free_func((GDestroyNotify)json_node_free);
    a->attachments = g_ptr_array_new_with_free_func((GDestroyNotify)g_object_unref);
    a->current_answer = g_string_new("");
    a->sidecar_sock = g_strdup(g_getenv("HYPHARNESS_SIDECAR"));
    if (!a->sidecar_sock)
        a->sidecar_sock = g_build_filename(
            g_get_user_runtime_dir(), "hyprharness", "sidecar.sock", NULL);
    a->control_sock = g_build_filename(
        g_get_user_runtime_dir(), "hyprneuro", "ui.sock", NULL);

    /* CSS. */
    GtkCssProvider *css = gtk_css_provider_new();
    gtk_css_provider_load_from_string(css,
        "window.hn-transparent { background: transparent; box-shadow: none; }"
        ".hn-panel { background-color: alpha(@theme_bg_color,0.96); color: @theme_fg_color;"
        " border: 1px solid alpha(@theme_fg_color,0.18); border-radius: 16px; padding: 12px; }"
        ".hn-panel textview, .hn-panel textview text { background: transparent; color: @theme_fg_color; }"
        "textview.hn-composer, textview.hn-composer text { background-color: #272727; color: #f0f0f0; caret-color: #f0f0f0; }"
        ".hn-composer { border-radius: 8px; padding: 8px; }"
        ".hn-input-action, .hn-input-action > button { min-width: 40px; min-height: 40px; padding: 0; border-radius: 999px; }"
        ".hn-status { font-size: 0.85em; }"
        ".hn-settings { font-size: 0.9em; }"
        ".hn-settings-title { font-weight: bold; font-size: 1.05em; }"
        ".hn-attach-strip { padding: 2px 0; }"
        ".hn-attach-item { padding: 2px 6px; border-radius: 4px; background-color: alpha(@theme_fg_color, 0.08); }"
        );
    gtk_style_context_add_provider_for_display(gdk_display_get_default(),
        GTK_STYLE_PROVIDER(css), GTK_STYLE_PROVIDER_PRIORITY_APPLICATION);
    GtkCssProvider *alpha = gtk_css_provider_new();
    gtk_css_provider_load_from_string(alpha,
        "window.background.hn-transparent { background-color: rgba(0,0,0,0); background-image: none;"
        " border: none; outline: none; box-shadow: none; }");
    gtk_style_context_add_provider_for_display(gdk_display_get_default(),
        GTK_STYLE_PROVIDER(alpha), GTK_STYLE_PROVIDER_PRIORITY_USER);
    g_object_unref(css);
    g_object_unref(alpha);

    /* Window: layer-shell TOP, bottom-right, 9px margin, exclusive_zone 0. */
    a->win = GTK_WINDOW(gtk_window_new());
    gtk_window_set_title(a->win, "Hyprneuro");
    gtk_window_set_decorated(a->win, FALSE);
    gtk_window_set_hide_on_close(a->win, TRUE);
    gtk_window_set_default_size(a->win, DEFAULT_WIDTH, -1);
    gtk_widget_add_css_class(GTK_WIDGET(a->win), "hn-transparent");
    gtk_layer_init_for_window(a->win);
    gtk_layer_set_layer(a->win, GTK_LAYER_SHELL_LAYER_TOP);
    gtk_layer_set_exclusive_zone(a->win, 0);
    gtk_layer_set_anchor(a->win, GTK_LAYER_SHELL_EDGE_BOTTOM, TRUE);
    gtk_layer_set_anchor(a->win, GTK_LAYER_SHELL_EDGE_RIGHT, TRUE);
    gtk_layer_set_margin(a->win, GTK_LAYER_SHELL_EDGE_BOTTOM, MARGIN_PX);
    gtk_layer_set_margin(a->win, GTK_LAYER_SHELL_EDGE_RIGHT, MARGIN_PX);
    gtk_layer_set_keyboard_mode(a->win, GTK_LAYER_SHELL_KEYBOARD_MODE_ON_DEMAND);

    /* Panel with GtkStack (chat page / settings page). */
    a->panel = gtk_box_new(GTK_ORIENTATION_VERTICAL, 8);
    gtk_widget_add_css_class(a->panel, "hn-panel");
    gtk_window_set_child(a->win, a->panel);

    a->stack = GTK_STACK(gtk_stack_new());
    gtk_box_append(GTK_BOX(a->panel), GTK_WIDGET(a->stack));

    /* ---- Chat page ---- */
    a->chat_page = gtk_box_new(GTK_ORIENTATION_VERTICAL, 8);

    a->transcript = gtk_text_view_new();
    gtk_text_view_set_editable(GTK_TEXT_VIEW(a->transcript), FALSE);
    gtk_text_view_set_wrap_mode(GTK_TEXT_VIEW(a->transcript), GTK_WRAP_WORD_CHAR);
    /* Create text tags once (avoids repeated creation warnings). */
    GtkTextBuffer *tbuf = gtk_text_view_get_buffer(GTK_TEXT_VIEW(a->transcript));
    a->tag_user = gtk_text_buffer_create_tag(tbuf, "user",
        "foreground", "#f0f0f0", "weight", PANGO_WEIGHT_BOLD, NULL);
    a->tag_asst = gtk_text_buffer_create_tag(tbuf, "asst",
        "foreground", "#9ecbff", "weight", PANGO_WEIGHT_BOLD, NULL);

    a->scroller = gtk_scrolled_window_new();
    gtk_scrolled_window_set_child(GTK_SCROLLED_WINDOW(a->scroller), a->transcript);
    gtk_scrolled_window_set_policy(GTK_SCROLLED_WINDOW(a->scroller),
        GTK_POLICY_NEVER, GTK_POLICY_AUTOMATIC);
    gtk_scrolled_window_set_max_content_height(GTK_SCROLLED_WINDOW(a->scroller),
        DEFAULT_WIDTH / 2);
    GtkAdjustment *vadj = gtk_scrolled_window_get_vadjustment(
        GTK_SCROLLED_WINDOW(a->scroller));
    g_signal_connect(vadj, "value-changed", G_CALLBACK(on_scroll_adjustment), a);
    gtk_box_append(GTK_BOX(a->chat_page), a->scroller);

    /* Media preview area (hidden until camera/audio active). */
    a->media_preview = gtk_box_new(GTK_ORIENTATION_VERTICAL, 4);
    gtk_widget_set_visible(a->media_preview, FALSE);
    a->camera_picture = gtk_picture_new();
    gtk_widget_set_size_request(a->camera_picture, 320, 240);
    gtk_picture_set_can_shrink(GTK_PICTURE(a->camera_picture), TRUE);
    gtk_box_append(GTK_BOX(a->media_preview), a->camera_picture);
    a->audio_level = gtk_level_bar_new_for_interval(0.0, 1.0);
    gtk_widget_set_visible(a->audio_level, FALSE);
    gtk_box_append(GTK_BOX(a->media_preview), a->audio_level);
    a->audio_timer_lbl = gtk_label_new("0:00");
    gtk_widget_set_visible(a->audio_timer_lbl, FALSE);
    gtk_box_append(GTK_BOX(a->media_preview), a->audio_timer_lbl);
    a->media_controls = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 6);
    a->media_label = gtk_label_new("");
    gtk_widget_set_hexpand(a->media_label, TRUE);
    gtk_label_set_xalign(GTK_LABEL(a->media_label), 0.0);
    gtk_box_append(GTK_BOX(a->media_controls), a->media_label);
    GtkWidget *cap_btn = gtk_button_new_with_label("Capture");
    g_signal_connect(cap_btn, "clicked", G_CALLBACK(on_camera_capture), a);
    gtk_box_append(GTK_BOX(a->media_controls), cap_btn);
    GtkWidget *astop_btn = gtk_button_new_with_label("Stop");
    g_signal_connect(astop_btn, "clicked", G_CALLBACK(on_audio_stop_btn), a);
    gtk_box_append(GTK_BOX(a->media_controls), astop_btn);
    GtkWidget *ascreen_btn = gtk_button_new_with_label("Screen");
    g_signal_connect(ascreen_btn, "clicked", G_CALLBACK(on_screen_capture), a);
    gtk_box_append(GTK_BOX(a->media_controls), ascreen_btn);
    GtkWidget *acancel_btn = gtk_button_new_with_label("Cancel");
    g_signal_connect(acancel_btn, "clicked", G_CALLBACK(on_camera_cancel), a);
    gtk_box_append(GTK_BOX(a->media_controls), acancel_btn);
    gtk_box_append(GTK_BOX(a->media_preview), a->media_controls);
    gtk_box_append(GTK_BOX(a->chat_page), a->media_preview);

    /* Attachment strip (hidden until files are selected). */
    a->attach_strip = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 4);
    gtk_widget_add_css_class(a->attach_strip, "hn-attach-strip");
    gtk_widget_set_visible(a->attach_strip, FALSE);
    gtk_box_append(GTK_BOX(a->chat_page), a->attach_strip);

    /* Composer: [attach] [input] [send] [audio] [vision] [size] [settings] */
    a->composer = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 6);
    gtk_widget_add_css_class(a->composer, "hn-composer");
    a->attach_btn = circular(a->composer, "list-add-symbolic",
                             G_CALLBACK(on_attach), a, "Attach file");
    a->input = GTK_TEXT_VIEW(gtk_text_view_new());
    gtk_widget_add_css_class(GTK_WIDGET(a->input), "hn-composer");
    gtk_text_view_set_wrap_mode(a->input, GTK_WRAP_WORD_CHAR);
    gtk_widget_set_hexpand(GTK_WIDGET(a->input), TRUE);
    gtk_widget_set_size_request(GTK_WIDGET(a->input), -1, 40);
    gtk_box_append(GTK_BOX(a->composer), GTK_WIDGET(a->input));
    a->send = circular(a->composer, "media-playback-start-symbolic",
                       G_CALLBACK(on_send_clicked), a, "Send");
    a->audio_btn = circular(a->composer,
                            "microphone-sensitivity-high-symbolic",
                            G_CALLBACK(on_audio), a, "Audio capture");
    a->vision_btn = circular(a->composer, "camera-photo-symbolic",
                             G_CALLBACK(on_vision), a, "Camera / Vision");
    a->size_toggle = circular(a->composer, "go-up-symbolic",
                              G_CALLBACK(on_size_toggle), a, "Transcript size");
    a->settings_btn = circular(a->composer, "emblem-system-symbolic",
                               G_CALLBACK(on_settings_open), a, "Settings");
    gtk_box_append(GTK_BOX(a->chat_page), a->composer);

    /* Status bar. */
    GtkWidget *statusrow = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 8);
    a->status = gtk_label_new("Hyprneuro · Local");
    gtk_widget_set_name(a->status, "hn-status");
    gtk_widget_add_css_class(a->status, "dim-label");
    gtk_label_set_xalign(GTK_LABEL(a->status), 0);
    gtk_widget_set_hexpand(a->status, TRUE);
    a->metrics = gtk_label_new("");
    gtk_widget_add_css_class(a->metrics, "dim-label");
    gtk_box_append(GTK_BOX(statusrow), a->status);
    gtk_box_append(GTK_BOX(statusrow), a->metrics);
    gtk_box_append(GTK_BOX(a->chat_page), statusrow);

    gtk_stack_add_named(a->stack, a->chat_page, "chat");

    /* ---- Settings page ---- */
    a->settings_page = gtk_box_new(GTK_ORIENTATION_VERTICAL, 0);
    GtkWidget *settings_header = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 8);
    GtkWidget *back_btn = gtk_button_new_with_label("← Back");
    g_signal_connect(back_btn, "clicked", G_CALLBACK(on_settings_back), a);
    GtkWidget *settings_title = gtk_label_new("Settings");
    gtk_widget_add_css_class(settings_title, "hn-settings-title");
    gtk_box_append(GTK_BOX(settings_header), back_btn);
    gtk_box_append(GTK_BOX(settings_header), settings_title);
    gtk_box_append(GTK_BOX(a->settings_page), settings_header);

    a->settings_scroll = gtk_scrolled_window_new();
    gtk_scrolled_window_set_policy(GTK_SCROLLED_WINDOW(a->settings_scroll),
        GTK_POLICY_NEVER, GTK_POLICY_AUTOMATIC);
    gtk_widget_set_vexpand(a->settings_scroll, TRUE);
    gtk_box_append(GTK_BOX(a->settings_page), a->settings_scroll);

    gtk_stack_add_named(a->stack, a->settings_page, "settings");
    gtk_stack_set_visible_child_name(a->stack, "chat");

    apply_transcript_size(a);

    /* Escape to hide / go back. */
    GtkEventController *key = gtk_event_controller_key_new();
    g_signal_connect(key, "key-pressed", G_CALLBACK(on_key), a);
    gtk_widget_add_controller(GTK_WIDGET(a->win), key);

    /* Control socket (ui.sock). */
    g_mkdir_with_parents(g_path_get_dirname(a->control_sock), 0700);
    g_unlink(a->control_sock);
    a->svc = g_socket_service_new();
    GSocketAddress *addr = g_unix_socket_address_new(a->control_sock);
    if (g_socket_listener_add_address(G_SOCKET_LISTENER(a->svc), addr,
            G_SOCKET_TYPE_STREAM, G_SOCKET_PROTOCOL_DEFAULT, NULL, NULL, NULL)) {
        g_signal_connect(a->svc, "incoming", G_CALLBACK(on_control_connect), a);
    }
    g_object_unref(addr);

    /* Monitoring poll. */
    a->monitor_timer = g_timeout_add(MONITOR_POLL_MS, poll_monitoring, a);

    GMainLoop *loop = g_main_loop_new(NULL, FALSE);
    a->loop = loop;
    show_ui(a);
    g_main_loop_run(loop);
    g_main_loop_unref(loop);

    /* Cleanup. */
    g_source_remove(a->monitor_timer);
    g_object_unref(a->svc);
    g_string_free(a->current_answer, TRUE);
    g_free(a->current_msg);
    g_ptr_array_free(a->history, TRUE);
    g_ptr_array_free(a->attachments, TRUE);
    g_free(a->sidecar_sock);
    g_free(a->control_sock);
    g_free(a);
    return 0;
}
