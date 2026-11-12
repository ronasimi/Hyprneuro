/* Hyprneuro: transparent GTK4 layer-shell overlay, bottom-right.
 *
 * A component of the Hyprneuro assistant. Talks to the Hyprneuro sidecar
 * over its Unix socket for monitoring, agent_chat (streaming), and ui_status.
 *
 * Architecture:
 *  - Chat streaming runs in a GTask worker thread; UI updates are posted
 *    to the main thread via g_idle_add().
 *  - Monitoring polls use a standalone connection (no shared socket state).
 *  - Settings view is a GtkStack page within the same window.
 *  - File picker uses GtkFileDialog (desktop backend selected by GTK).
 *  - History owns builder roots; embedding transfers copies to builders.
 *
 * Layer-shell: TOP layer, anchored bottom+right, 9px margin, exclusive_zone 0.
 */
#include <gtk/gtk.h>
#include <gtk4-layer-shell/gtk4-layer-shell.h>
#include <json-glib/json-glib.h>
#include <glib-unix.h>
#include <gio/gunixsocketaddress.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/time.h>
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
    gboolean snapshot_busy;
    char *ui_data, *mon_data;
    gboolean user_scrolled_up;

    GtkTextTag *tag_user, *tag_asst;

    GString *current_answer;
    char *current_msg;

    GPtrArray *attachments;
    char *attachment_b64, *attachment_mime;
    GCancellable *picker_cancel;

    /* Media preview area. */
    GtkWidget *media_preview;
    GtkWidget *media_controls;
    GtkWidget *media_label;
};

/* ---- utility ------------------------------------------------------------- */
static JsonNode *jmember(JsonNode *node, const char *key) {
    if (!node || !JSON_NODE_HOLDS_OBJECT(node)) return NULL;
    return json_object_get_member(json_node_get_object(node), key);
}

static const char *jstr(JsonNode *node) {
    return node && JSON_NODE_HOLDS_VALUE(node) &&
        json_node_get_value_type(node) == G_TYPE_STRING ? json_node_get_string(node) : NULL;
}

static double jnum(JsonNode *n, double def) {
    if (!n) return def;
    if (JSON_NODE_HOLDS_VALUE(n)) {
        GType t = json_node_get_value_type(n);
        if (t == G_TYPE_DOUBLE) return json_node_get_double(n);
        if (t == G_TYPE_INT64) return (double)json_node_get_int(n);
    }
    return def;
}

static void set_status(App *a, const char *text) {
    gtk_label_set_text(GTK_LABEL(a->status), text);
    gtk_widget_set_tooltip_text(a->status, text);
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

static void on_scroll_adjustment(GtkAdjustment *adj, App *a) {
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
            gtk_widget_set_size_request(a->scroller, DEFAULT_WIDTH,
                a->attachments->len ? DEFAULT_WIDTH / 2 : DEFAULT_WIDTH);
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
    /* get_root transfers a full reference to the caller. */
    g_ptr_array_add(a->history, json_builder_get_root(hb));
    g_object_unref(hb);
}

static char *history_to_json(App *a) {
    JsonBuilder *b = json_builder_new();
    json_builder_begin_array(b);
    for (guint i = 0; i < a->history->len; i++) {
        JsonNode *node = g_ptr_array_index(a->history, i);
        json_builder_add_value(b, json_node_copy(node));
    }
    json_builder_end_array(b);
    JsonGenerator *g = json_generator_new();
    JsonNode *root = json_builder_get_root(b);
    json_generator_set_root(g, root);
    json_node_unref(root);
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
    JsonNode *root = json_builder_get_root(b);
    json_generator_set_root(g, root);
    json_node_unref(root);
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
    GString *response = g_string_new(NULL);
    gboolean complete = FALSE;
    while (response->len < 1024 * 1024) {
        char byte;
        if (g_input_stream_read(G_INPUT_STREAM(stream), &byte, 1, NULL, err) != 1) break;
        if (byte == '\n') { complete = TRUE; break; }
        g_string_append_c(response, byte);
    }
    char *resp = g_string_free(response, !complete);
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
/* These callbacks run in the MAIN thread (posted via g_idle_add). */

static gboolean on_delta(gpointer data) {
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
    return G_SOURCE_REMOVE;
}

static void clear_attachments(App *a);

static gboolean on_chat_done(gpointer data) {
    ChatDoneData *d = data;
    App *a = d->app;
    a->busy = FALSE;
    gtk_widget_set_sensitive(a->send, TRUE);
    gtk_widget_set_sensitive(a->attach_btn, TRUE);
    gtk_widget_set_sensitive(a->attach_strip, TRUE);

    if (d->success) {
        set_status(a, "Hyprneuro · Local");
        clear_attachments(a);
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
    return G_SOURCE_REMOVE;
}

/* Worker thread: blocking socket I/O, posts UI updates to main thread. */
static void chat_worker(GTask *task, gpointer source, gpointer task_data,
                        GCancellable *canc) {
    (void)source; (void)canc;
    ChatTaskData *d = task_data;
    App *a = d->app;

    /* Connect to sidecar. */
    int fd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
    if (fd < 0) {
        ChatDoneData *dd = g_new0(ChatDoneData, 1);
        dd->app = a; dd->success = FALSE;
        dd->error = g_strdup("socket() failed");
        g_idle_add(on_chat_done, dd);
        goto cleanup;
    }
    struct timeval timeout = {.tv_sec = 120};
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof timeout);
    setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof timeout);

    struct sockaddr_un addr = {0};
    addr.sun_family = AF_UNIX;
    g_strlcpy(addr.sun_path, d->sock_path, sizeof(addr.sun_path));
    if (connect(fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        ChatDoneData *dd = g_new0(ChatDoneData, 1);
        dd->app = a; dd->success = FALSE;
        dd->error = g_strdup_printf("connect: %s", strerror(errno));
        g_idle_add(on_chat_done, dd);
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
            json_builder_add_value(b, json_node_copy(json_parser_get_root(hp)));
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
    JsonNode *root = json_builder_get_root(b);
    json_generator_set_root(g, root);
    json_node_unref(root);
    char *req = json_generator_to_data(g, NULL);
    char *frame = g_strconcat(req, "\n", NULL);

    gsize offset = 0, length = strlen(frame);
    while (offset < length) {
        ssize_t n = send(fd, frame + offset, length - offset, MSG_NOSIGNAL);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) break;
        offset += n;
    }
    g_free(frame); g_free(req);
    g_object_unref(g); g_object_unref(b);
    if (offset != length) {
        ChatDoneData *dd = g_new0(ChatDoneData, 1);
        dd->app = a; dd->success = FALSE;
        dd->error = g_strdup("write failed");
        g_idle_add(on_chat_done, dd);
        close(fd);
        goto cleanup;
    }

    /* Read streaming lines. */
    GString *line_buf = g_string_new("");
    char rbuf[8192];
    gboolean done = FALSE;
    gsize answer_bytes = 0;
    while (!done) {
        ssize_t n = read(fd, rbuf, sizeof(rbuf));
        if (n <= 0) break;
        for (ssize_t i = 0; i < n && !done; i++) {
            char c = rbuf[i];
            if (c == '\n') {
                char *line = g_strdup(line_buf->str);
                g_string_truncate(line_buf, 0);
                if (line[0]) {
                    JsonParser *p = json_parser_new();
                    if (json_parser_load_from_data(p, line, -1, NULL)) {
                        JsonNode *r = json_parser_get_root(p);
                        JsonNode *tn = jmember(r, "type");
                        const char *type = jstr(tn);
                        if (type && !g_strcmp0(type, "delta")) {
                            JsonNode *dn = jmember(r, "text");
                            const char *txt = jstr(dn);
                            if (!txt || (answer_bytes += strlen(txt)) > 1024 * 1024) {
                                g_object_unref(p); g_free(line); goto stream_end;
                            }
                            DeltaData *dd = g_new0(DeltaData, 1);
                            dd->app = a;
                            dd->text = g_strdup(txt);
                            g_idle_add(on_delta, dd);
                        } else if (type && !g_strcmp0(type, "done")) {
                            ChatDoneData *cd = g_new0(ChatDoneData, 1);
                            cd->app = a; cd->success = TRUE;
                            g_idle_add(on_chat_done, cd);
                            done = TRUE;
                        } else if (type && !g_strcmp0(type, "error")) {
                            const char *em = jstr(jmember(r, "error"));
                            ChatDoneData *cd = g_new0(ChatDoneData, 1);
                            cd->app = a; cd->success = FALSE;
                            cd->error = g_strdup(em ? em : "Invalid error frame");
                            g_idle_add(on_chat_done, cd);
                            done = TRUE;
                        }
                    }
                    g_object_unref(p);
                }
                g_free(line);
            } else {
                if (line_buf->len >= 1024 * 1024) goto stream_end;
                g_string_append_c(line_buf, c);
            }
        }
    }
stream_end:
    close(fd);
    g_string_free(line_buf, TRUE);

    /* If we exited the read loop without a done/error frame, report it. */
    if (!done) {
        ChatDoneData *cd = g_new0(ChatDoneData, 1);
        cd->app = a; cd->success = FALSE;
        cd->error = g_strdup("Connection closed, timed out, or invalid/oversized stream");
        g_idle_add(on_chat_done, cd);
    }

cleanup:
    g_task_return_boolean(task, TRUE);
    g_free(d->sock_path);
    g_free(d->message);
    g_free(d->history_json);
    g_free(d->media_b64);
    g_free(d->media_mime);
    g_free(d);
}

static void clear_attachments(App *a) {
    g_ptr_array_set_size(a->attachments, 0);
    g_clear_pointer(&a->attachment_b64, g_free);
    g_clear_pointer(&a->attachment_mime, g_free);
    GtkWidget *child;
    while ((child = gtk_widget_get_first_child(a->attach_strip)))
        gtk_box_remove(GTK_BOX(a->attach_strip), child);
    gtk_widget_set_visible(a->attach_strip, FALSE);
    apply_transcript_size(a);
}
typedef struct { int width, height; gboolean allowed; } ImageSize;
static void image_size_prepared(GdkPixbufLoader *loader, int width, int height, gpointer data) {
    ImageSize *size = data;
    size->width = width; size->height = height;
    size->allowed = width > 0 && height > 0 && width <= 4096 && height <= 4096;
    if (!size->allowed) {
        gdk_pixbuf_loader_set_size(loader, 1, 1);
        return;
    }
    double scale = MIN(1.0, MIN(640.0 / width, 360.0 / height));
    gdk_pixbuf_loader_set_size(loader, MAX(1, (int)(width * scale)),
                                      MAX(1, (int)(height * scale)));
}
static gboolean load_image(GFile *file, char **b64, char **mime,
                           GdkPixbuf **preview, gsize *length, ImageSize *size) {
    if (!g_file_is_native(file)) return FALSE;
    GFileInputStream *in = g_file_read(file, NULL, NULL);
    if (!in) return FALSE;
    gsize limit = 5 * 1024 * 1024, len = 0;
    guchar *bytes = g_malloc(limit + 1);
    gboolean ok = g_input_stream_read_all(G_INPUT_STREAM(in), bytes, limit + 1,
                                         &len, NULL, NULL);
    g_object_unref(in);
    char *type = g_content_type_guess(NULL, bytes, len, NULL);
    ok = ok && len > 0 && len <= limit &&
        (!g_strcmp0(type, "image/png") || !g_strcmp0(type, "image/jpeg") ||
         !g_strcmp0(type, "image/webp"));
    GdkPixbufLoader *loader = ok ? gdk_pixbuf_loader_new_with_mime_type(type, NULL) : NULL;
    if (loader) {
        g_signal_connect(loader, "size-prepared", G_CALLBACK(image_size_prepared), size);
        ok = gdk_pixbuf_loader_write(loader, bytes, len, NULL);
        gboolean closed = gdk_pixbuf_loader_close(loader, NULL);
        GdkPixbuf *image = gdk_pixbuf_loader_get_pixbuf(loader);
        GdkPixbufAnimation *animation = gdk_pixbuf_loader_get_animation(loader);
        ok = ok && closed && image && size->allowed && animation &&
             gdk_pixbuf_animation_is_static_image(animation);
        if (ok) *preview = g_object_ref(image);
        g_object_unref(loader);
    } else {
        ok = FALSE;
    }
    if (ok) {
        /* Payload is the same bounded snapshot that was decoded for review. */
        *b64 = g_base64_encode(bytes, len);
        *mime = g_strdup(type);
        *length = len;
    }
    g_free(type); g_free(bytes);
    return ok;
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

    td->media_b64 = g_strdup(a->attachment_b64);
    td->media_mime = g_strdup(a->attachment_mime);
    gtk_widget_set_sensitive(a->attach_btn, FALSE);
    gtk_widget_set_sensitive(a->attach_strip, FALSE);

    GTask *task = g_task_new(NULL, NULL, NULL, NULL);
    g_task_set_task_data(task, td, NULL); /* worker frees it */
    g_task_run_in_thread(task, chat_worker);
    g_object_unref(task);
    g_free(msg);
}

/* ---- monitoring poll (standalone connection) ----------------------------- */
static void populate_settings(App *a);
typedef struct { char *ui, *mon; } Snapshot;
static void snapshot_worker(GTask *task, gpointer source, gpointer data, GCancellable *cancel) {
    (void)source; (void)cancel;
    Snapshot *snapshot = g_new0(Snapshot, 1);
    snapshot->mon = sidecar_call(data, "monitoring", NULL);
    snapshot->ui = sidecar_call(data, "ui_status", NULL);
    g_task_return_pointer(task, snapshot, NULL);
}
static void snapshot_ready(GObject *source, GAsyncResult *result, gpointer data) {
    (void)source;
    App *a = data;
    Snapshot *snapshot = g_task_propagate_pointer(G_TASK(result), NULL);
    g_free(a->ui_data); g_free(a->mon_data);
    a->ui_data = snapshot->ui; a->mon_data = snapshot->mon;
    g_free(snapshot);
    a->snapshot_busy = FALSE;
    char *mon_data = g_strdup(a->mon_data);
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

    }
    /* Settings is a stable read-only snapshot, refreshed on next open. */
}
static gboolean poll_monitoring(gpointer data) {
    App *a = data;
    if (!a->snapshot_busy) {
        a->snapshot_busy = TRUE;
        GTask *task = g_task_new(NULL, NULL, snapshot_ready, a);
        g_task_set_task_data(task, g_strdup(a->sidecar_sock), g_free);
        g_task_run_in_thread(task, snapshot_worker);
        g_object_unref(task);
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
    if (child) gtk_scrolled_window_set_child(GTK_SCROLLED_WINDOW(a->settings_scroll), NULL);

    GtkWidget *content = gtk_box_new(GTK_ORIENTATION_VERTICAL, 4);
    gtk_widget_set_margin_start(content, 12);
    gtk_widget_set_margin_end(content, 12);
    gtk_widget_set_margin_top(content, 8);
    gtk_widget_set_margin_bottom(content, 8);

    /* Models & Inference */
    add_settings_section(content, "Status (read-only; no settings switches)");
    add_settings_section(content, "Models & Inference");
    GtkWidget *model_list = gtk_list_box_new();
    gtk_widget_add_css_class(model_list, "hn-settings");
    char *ui_data = g_strdup(a->ui_data);
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
    char *mon_data = g_strdup(a->mon_data);
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
                    JsonNode *app_class = jmember(focused, "app_class");
                    if (app_class && json_node_get_value_type(app_class) == G_TYPE_STRING)
                        add_settings_row(GTK_LIST_BOX(mon_list), "Focused app",
                                         json_node_get_string(app_class));
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
    poll_monitoring(a);
    gtk_stack_set_visible_child_name(a->stack, "settings");
}

/* ---- file picker (portal-backed via GtkFileDialog) ----------------------- */
static void on_attachment_remove(GtkButton *btn, gpointer data) {
    (void)btn;
    clear_attachments(data);
    set_status(data, "Hyprneuro · attachment removed");
}
static GdkTexture *preview_texture(GdkPixbuf *pixbuf) {
    int width = gdk_pixbuf_get_width(pixbuf), height = gdk_pixbuf_get_height(pixbuf);
    int stride = gdk_pixbuf_get_rowstride(pixbuf);
    guchar *pixels = g_malloc0((gsize)stride * height);
    memcpy(pixels, gdk_pixbuf_get_pixels(pixbuf), gdk_pixbuf_get_byte_length(pixbuf));
    GBytes *bytes = g_bytes_new_take(pixels, (gsize)stride * height);
    GdkTexture *texture = gdk_memory_texture_new(width, height,
        gdk_pixbuf_get_has_alpha(pixbuf) ? GDK_MEMORY_R8G8B8A8 : GDK_MEMORY_R8G8B8,
        bytes, stride);
    g_bytes_unref(bytes);
    return texture;
}
static void on_file_dialog_open(GObject *obj, GAsyncResult *result, gpointer data) {
    App *a = data;
    GError *err = NULL;
    g_clear_object(&a->picker_cancel);
    gtk_layer_set_keyboard_mode(a->win, GTK_LAYER_SHELL_KEYBOARD_MODE_ON_DEMAND);
    gtk_widget_set_sensitive(a->attach_btn, !a->busy);
    GFile *file = gtk_file_dialog_open_finish(GTK_FILE_DIALOG(obj), result, &err);
    if (!file) {
        if (err && !g_error_matches(err, GTK_DIALOG_ERROR, GTK_DIALOG_ERROR_DISMISSED) &&
            !g_error_matches(err, GTK_DIALOG_ERROR, GTK_DIALOG_ERROR_CANCELLED))
            set_status(a, "File picker failed (no attachment selected)");
        g_clear_error(&err);
        return;
    }
    if (a->busy) { g_object_unref(file); return; }
    char *b64 = NULL, *mime = NULL;
    GdkPixbuf *preview = NULL;
    gsize length = 0;
    ImageSize size = {0};
    if (!load_image(file, &b64, &mime, &preview, &length, &size)) {
        set_status(a, "Rejected: static PNG/JPEG/WebP only, ≤5 MiB, ≤4096×4096; decoder required");
        g_object_unref(file);
        return;
    }
    clear_attachments(a);
    a->attachment_b64 = b64; a->attachment_mime = mime;
    g_ptr_array_add(a->attachments, file);
    apply_transcript_size(a);
    char *name = g_file_get_basename(file);
    char *formatted_size = g_format_size_full(length, G_FORMAT_SIZE_IEC_UNITS);
    char *metadata = g_strdup_printf("%s\n%s · %s · %d × %d", name, mime,
                                      formatted_size, size.width, size.height);
    GtkWidget *item = gtk_box_new(GTK_ORIENTATION_VERTICAL, 4);
    gtk_widget_add_css_class(item, "hn-attach-item");
    GtkWidget *summary = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 8);
    double review_scale = MIN(480.0 / gdk_pixbuf_get_width(preview),
                              240.0 / gdk_pixbuf_get_height(preview));
    GdkPixbuf *review_pixels = gdk_pixbuf_scale_simple(preview,
        MAX(1, (int)(gdk_pixbuf_get_width(preview) * review_scale)),
        MAX(1, (int)(gdk_pixbuf_get_height(preview) * review_scale)), GDK_INTERP_BILINEAR);
    GdkTexture *texture = preview_texture(review_pixels);
    g_object_unref(review_pixels);
    double thumb_scale = MIN(112.0 / gdk_pixbuf_get_width(preview),
                             72.0 / gdk_pixbuf_get_height(preview));
    GdkPixbuf *small = gdk_pixbuf_scale_simple(preview,
        MAX(1, (int)(gdk_pixbuf_get_width(preview) * thumb_scale)),
        MAX(1, (int)(gdk_pixbuf_get_height(preview) * thumb_scale)), GDK_INTERP_BILINEAR);
    g_object_unref(preview);
    GdkTexture *thumb_texture = preview_texture(small);
    g_object_unref(small);
    GtkWidget *thumbnail = gtk_picture_new_for_paintable(GDK_PAINTABLE(thumb_texture));
    g_object_unref(thumb_texture);
    gtk_picture_set_content_fit(GTK_PICTURE(thumbnail), GTK_CONTENT_FIT_CONTAIN);
    gtk_widget_set_halign(thumbnail, GTK_ALIGN_CENTER);
    gtk_widget_set_valign(thumbnail, GTK_ALIGN_CENTER);
    gtk_box_append(GTK_BOX(summary), thumbnail);
    GtkWidget *label = gtk_label_new(metadata);
    gtk_label_set_xalign(GTK_LABEL(label), 0);
    gtk_label_set_ellipsize(GTK_LABEL(label), PANGO_ELLIPSIZE_MIDDLE);
    gtk_widget_set_tooltip_text(label, metadata);
    gtk_widget_set_hexpand(label, TRUE);
    gtk_box_append(GTK_BOX(summary), label);
    GtkWidget *rm = gtk_button_new_from_icon_name("window-close-symbolic");
    gtk_widget_set_tooltip_text(rm, "Remove attachment (also removes it from submission)");
    g_signal_connect(rm, "clicked", G_CALLBACK(on_attachment_remove), a);
    gtk_box_append(GTK_BOX(summary), rm);
    gtk_box_append(GTK_BOX(item), summary);
    GtkWidget *review = gtk_expander_new("Review image (bounded preview)");
    GtkWidget *picture = gtk_picture_new_for_paintable(GDK_PAINTABLE(texture));
    gtk_picture_set_content_fit(GTK_PICTURE(picture), GTK_CONTENT_FIT_CONTAIN);
    gtk_widget_set_size_request(picture, gdk_texture_get_width(texture), gdk_texture_get_height(texture));
    /* A fixed review canvas bounds height-for-width measurement as well as
     * pixels; GtkPicture alone can make an expanded layer taller than output. */
    GtkWidget *canvas = gtk_fixed_new();
    gtk_widget_set_size_request(canvas, 480, 240);
    gtk_widget_set_halign(canvas, GTK_ALIGN_CENTER);
    gtk_fixed_put(GTK_FIXED(canvas), picture,
                  (480 - gdk_texture_get_width(texture)) / 2.0,
                  (240 - gdk_texture_get_height(texture)) / 2.0);
    gtk_expander_set_child(GTK_EXPANDER(review), canvas);
    gtk_box_append(GTK_BOX(item), review);
    g_object_unref(texture);
    gtk_box_append(GTK_BOX(a->attach_strip), item);
    g_free(name); g_free(formatted_size); g_free(metadata);
    gtk_widget_set_visible(a->attach_strip, TRUE);
    set_status(a, "One reviewed image attached · audio/video/documents unsupported");
}

static void on_attach(GtkButton *btn, gpointer data) {
    (void)btn;
    App *a = data;
    GtkFileDialog *dialog = gtk_file_dialog_new();
    gtk_file_dialog_set_title(dialog, "Select static image (PNG/JPEG/WebP; ≤5 MiB, ≤4096×4096)");
    /* Layer surfaces are not xdg_toplevels: exporting one as the portal
     * parent disconnects this client on Hyprland. Use an unparented portal. */
    gtk_layer_set_keyboard_mode(a->win, GTK_LAYER_SHELL_KEYBOARD_MODE_NONE);
    a->picker_cancel = g_cancellable_new();
    gtk_widget_set_sensitive(a->attach_btn, FALSE);
    gtk_file_dialog_open(dialog, NULL, a->picker_cancel, on_file_dialog_open, a);
    g_object_unref(dialog);
}

/* Capture is deliberately unavailable until portal consent and release exist.
 * Do not fall back to raw PipeWire or grim (neither enforces portal consent). */
static void on_camera_capture(GtkButton *btn, gpointer data) {
    (void)btn; set_status(data, "Camera unavailable: portal capture not implemented");
}
static void on_screen_capture(GtkButton *btn, gpointer data) {
    (void)btn; set_status(data, "Screen unavailable: portal capture not implemented");
}
static void on_camera_cancel(GtkButton *btn, gpointer data) {
    (void)btn;
    App *a = data;
    gtk_widget_set_visible(a->media_preview, FALSE);
    set_status(a, "Hyprneuro · capture closed (no devices opened)");
}
static void on_vision(GtkButton *btn, gpointer data) {
    on_camera_capture(btn, data);
    App *a = data;
    gtk_widget_set_visible(a->media_preview, TRUE);
    gtk_label_set_text(GTK_LABEL(a->media_label), "Capture unavailable (portal required)");
}
static void on_audio_stop_btn(GtkButton *btn, gpointer data) {
    on_camera_cancel(btn, data);
}
static void on_audio(GtkButton *btn, gpointer data) {
    on_vision(btn, data);
    set_status(data, "Audio unavailable: portal recording not implemented");
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
    if (a->picker_cancel) g_cancellable_cancel(a->picker_cancel);
    gtk_widget_set_visible(a->media_preview, FALSE);
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
typedef struct {
    App *app;
    GSocketConnection *conn;
    GCancellable *cancel;
    guint timeout;
    char buffer[16];
    gsize used;
} ControlRead;
static gboolean control_timeout(gpointer data) {
    ControlRead *r = data;
    r->timeout = 0;
    g_cancellable_cancel(r->cancel);
    return G_SOURCE_REMOVE;
}
static void control_ready(GObject *source, GAsyncResult *result, gpointer data) {
    ControlRead *r = data;
    gssize n = g_input_stream_read_finish(G_INPUT_STREAM(source), result, NULL);
    if (n > 0) {
        r->used += n;
        char *newline = memchr(r->buffer, '\n', r->used);
        if (newline) {
            *newline = 0;
            if (!strcmp(r->buffer, "toggle")) toggle_ui(r->app);
            else if (!strcmp(r->buffer, "show")) show_ui(r->app);
            else if (!strcmp(r->buffer, "hide")) hide_ui(r->app);
        } else if (r->used < sizeof r->buffer) {
            g_input_stream_read_async(G_INPUT_STREAM(source), r->buffer + r->used,
                sizeof r->buffer - r->used, G_PRIORITY_DEFAULT, r->cancel, control_ready, r);
            return;
        }
    }
    if (r->timeout) g_source_remove(r->timeout);
    g_object_unref(r->cancel);
    g_object_unref(r->conn);
    g_free(r);
}
static gboolean on_control_connect(GSocketService *svc, GSocketConnection *conn,
                                   GObject *source, gpointer data) {
    (void)svc; (void)source;
    ControlRead *r = g_new0(ControlRead, 1);
    r->app = data;
    r->conn = g_object_ref(conn); /* incoming borrows the connection */
    r->cancel = g_cancellable_new();
    r->timeout = g_timeout_add_seconds(2, control_timeout, r);
    g_input_stream_read_async(g_io_stream_get_input_stream(G_IO_STREAM(conn)),
        r->buffer, sizeof r->buffer, G_PRIORITY_DEFAULT, r->cancel, control_ready, r);
    return TRUE;
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
    gtk_widget_add_css_class(btn, "hn-input-action");
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

/* Run before GtkTextView's default Return binding, so sending never also
 * inserts a newline (including when send_message rejects busy/empty input). */
static gboolean on_input_key(GtkEventControllerKey *controller, guint keyval,
                             guint code, GdkModifierType state, gpointer data) {
    (void)controller; (void)code;
    App *a = data;
    if (keyval != GDK_KEY_Return && keyval != GDK_KEY_KP_Enter) return FALSE;
    if (state & GDK_CONTROL_MASK) {
        GtkTextBuffer *buffer = gtk_text_view_get_buffer(a->input);
        gtk_text_buffer_insert_at_cursor(buffer, "\n", 1);
    } else {
        send_message(a);
    }
    return TRUE;
}

/* ---- main ---------------------------------------------------------------- */
int main(int argc, char **argv) {
    (void)argc; (void)argv;
    gtk_init();
    App *a = g_new0(App, 1);
    a->size = SIZE_RESTORE;
    a->history = g_ptr_array_new_with_free_func((GDestroyNotify)json_node_unref);
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
    a->attach_strip = gtk_box_new(GTK_ORIENTATION_VERTICAL, 4);
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
    gtk_widget_set_tooltip_text(GTK_WIDGET(a->input), "Enter sends · Ctrl+Enter inserts a newline");
    GtkEventController *input_key = gtk_event_controller_key_new();
    gtk_event_controller_set_propagation_phase(input_key, GTK_PHASE_CAPTURE);
    g_signal_connect(input_key, "key-pressed", G_CALLBACK(on_input_key), a);
    gtk_widget_add_controller(GTK_WIDGET(a->input), input_key);
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
    gtk_label_set_ellipsize(GTK_LABEL(a->status), PANGO_ELLIPSIZE_END);
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
    char *control_dir = g_path_get_dirname(a->control_sock);
    g_mkdir_with_parents(control_dir, 0700);
    g_free(control_dir);
    g_unlink(a->control_sock);
    a->svc = g_socket_service_new();
    GSocketAddress *addr = g_unix_socket_address_new(a->control_sock);
    if (g_socket_listener_add_address(G_SOCKET_LISTENER(a->svc), addr,
            G_SOCKET_TYPE_STREAM, G_SOCKET_PROTOCOL_DEFAULT, NULL, NULL, NULL)) {
        g_signal_connect(a->svc, "incoming", G_CALLBACK(on_control_connect), a);
    }
    g_object_unref(addr);

    /* Monitoring poll. */
    poll_monitoring(a);
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
    g_free(a->attachment_b64);
    g_free(a->attachment_mime);
    g_free(a->sidecar_sock);
    g_free(a->control_sock);
    g_free(a);
    return 0;
}
