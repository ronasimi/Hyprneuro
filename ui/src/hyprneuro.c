/* Hyprneuro: transparent GTK4 layer-shell overlay, bottom-right.
 *
 * A component of the Hyprneuro assistant. Reuses the Jeevus dark-composer
 * design. Talks to the Hyprneuro sidecar over its Unix socket for:
 *   - monitoring snapshot (status bar)
 *   - agent_chat (streaming responses into the transcript)
 *   - ui_status (model health)
 * A control socket (ui.sock) accepts toggle/show/hide from `hyprneuro ui`.
 *
 * Layer-shell: TOP layer, anchored bottom+right, 9px margin, exclusive_zone 0,
 * ON_DEMAND keyboard. Transparent surface; clicks outside pass through.
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

#define MARGIN_PX 9
#define DEFAULT_WIDTH 656
#define MONITOR_POLL_MS 2000

typedef enum { SIZE_COMPACT, SIZE_RESTORE, SIZE_FULL } TranscriptSize;

typedef struct {
    GtkWindow *win;
    GtkWidget *panel, *transcript, *scroller, *composer, *status, *metrics;
    GtkTextView *input;
    GtkWidget *send, *size_toggle, *attach, *audio, *vision;
    GSocketConnection *sock;  /* active sidecar connection (a GIOStream) */
    GSocketService *svc;      /* control service (ui.sock) */
    char *sidecar_sock;
    char *control_sock;
    GMainLoop *loop;
    TranscriptSize size;
    gboolean shown, busy;
    GPtrArray *history;       /* of {role, content} JsonObjects (bounded) */
    guint monitor_timer;
    gboolean user_scrolled_up;
} App;

/* ---- sidecar IPC (one request / one-or-more JSON lines) ----------------- */
static GSocketConnection *connect_sidecar(App *a) {
    GSocketClient *client = g_socket_client_new();
    GSocketAddress *addr = g_unix_socket_address_new(a->sidecar_sock);
    GSocketConnection *c = g_socket_client_connect(
        client, G_SOCKET_CONNECTABLE(addr), NULL, NULL);
    g_object_unref(addr);
    g_object_unref(client);
    return c; /* NULL on failure */
}
/* Read one newline-terminated JSON object from a socket. */
static gboolean read_one_line(GSocketConnection *sock, char **line_out, GCancellable *canc, GError **err) {
    GDataInputStream *stream = g_data_input_stream_new(g_io_stream_get_input_stream(G_IO_STREAM(sock)));
    char *line = g_data_input_stream_read_line(stream, NULL, canc, err);
    g_object_unref(stream);
    if (!line) return FALSE;
    *line_out = line;
    return TRUE;
}

/* Safe member accessor: json_object_get_member on the node's object. */
static JsonNode *jmember(JsonNode *node, const char *key) {
    if (!node || !JSON_NODE_HOLDS_OBJECT(node)) return NULL;
    return json_object_get_member(json_node_get_object(node), key);
}

/* Safe number accessor: returns def if the node is not an int/double. */
static double jnum(JsonNode *n, double def) {
    if (!n) return def;
    JsonNodeType t = json_node_get_node_type(n);
    if (t == G_TYPE_DOUBLE) return json_node_get_double(n);
    if (t == G_TYPE_INT) return (double)json_node_get_int(n);
    return def;
}

/* Fire a request, read the single response, return its "result" node. */
/* Fire a request, read the single response, return the "result" as a JSON
 * string (caller g_free's it), or NULL on error. A string avoids owning a node
 * whose parent parser is freed on return. */
static char *sidecar_call(App *a, const char *action, JsonObject *extra, GError **err) {
    g_clear_object(&a->sock);
    a->sock = connect_sidecar(a);
    if (!a->sock) { g_set_error(err, G_IO_ERROR, G_IO_ERROR_CONNECTION_REFUSED, "sidecar unavailable"); return NULL; }
    JsonBuilder *b = json_builder_new();
    json_builder_begin_object(b);
    json_builder_set_member_name(b, "action"); json_builder_add_string_value(b, action);
    (void)extra; /* flat request; extra members unused */
    json_builder_end_object(b);
    JsonGenerator *g = json_generator_new();
    json_generator_set_root(g, json_builder_get_root(b));
    char *req = json_generator_to_data(g, NULL);
    char *frame = g_strconcat(req, "\n", NULL);
    gsize written;
    GOutputStream *out = g_io_stream_get_output_stream(G_IO_STREAM(a->sock));
    if (!g_output_stream_write_all(out, frame, strlen(frame), &written, NULL, err)) {
        g_free(frame); g_free(req); g_object_unref(g); g_object_unref(b);
        return NULL;
    }
    char *resp = NULL;
    if (!read_one_line(a->sock, &resp, NULL, err)) {
        g_free(frame); g_free(req); g_object_unref(g); g_object_unref(b);
        return NULL;
    }
    g_free(frame); g_free(req);
    JsonParser *p = json_parser_new();
    char *result_str = NULL;
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
    g_free(resp); g_object_unref(p); g_object_unref(g); g_object_unref(b);
    return result_str; /* caller g_free's it */
}

/* ---- UI updates ---------------------------------------------------------- */
static void set_status(App *a, const char *text) { gtk_label_set_text(GTK_LABEL(a->status), text); }

static void transcript_append(App *a, const char *who, const char *text) {
    /* Simple: append a styled paragraph. Real Markdown rendering is a follow-up. */
    GtkTextBuffer *buf = gtk_text_view_get_buffer(GTK_TEXT_VIEW(a->transcript));
    GtkTextIter end; gtk_text_buffer_get_end_iter(buf, &end);
    GtkTextTag *tag = gtk_text_buffer_create_tag(buf, who, "foreground",
        g_strcmp0(who, "user") ? "#9ecbff" : "#f0f0f0", "weight",
        who[0] ? PANGO_WEIGHT_BOLD : PANGO_WEIGHT_NORMAL, NULL);
    char *styled = g_strdup_printf("\n%s: %s\n", who, text);
    gtk_text_buffer_insert_with_tags_by_name(buf, &end, styled, -1, who, NULL);
    g_free(styled);
    /* Autoscroll to bottom unless the user scrolled up. */
    if (!a->user_scrolled_up) {
        gtk_text_buffer_get_end_iter(buf, &end);
        GtkTextBuffer *b2 = gtk_text_view_get_buffer(GTK_TEXT_VIEW(a->transcript));
        GtkTextMark *m = gtk_text_buffer_create_mark(b2, NULL, &end, FALSE);
        gtk_text_view_scroll_to_mark(GTK_TEXT_VIEW(a->transcript), m, 0.0, TRUE, 0, 1.0);
        gtk_text_buffer_delete_mark(b2, m);
    }
}

static void on_scroll_adjustment(App *a, GtkAdjustment *adj) {
    double upper = gtk_adjustment_get_upper(adj);
    double val = gtk_adjustment_get_value(adj);
    double page = gtk_adjustment_get_page_size(adj);
    a->user_scrolled_up = (upper - (val + page)) > 8.0;
}

static void apply_transcript_size(App *a) {
    /* compact: hide transcript; restore: ~2:1; full: ~1:1 (of the width). */
    switch (a->size) {
        case SIZE_COMPACT:
            gtk_widget_set_visible(a->scroller, FALSE);
            gtk_widget_set_size_request(a->scroller, DEFAULT_WIDTH, -1);
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

/* ---- agent chat (streaming) --------------------------------------------- */
static void push_history(App *a, const char *role, const char *content) {
    if (a->history->len >= 20)
        json_node_free(g_ptr_array_remove_index(a->history, 0));
    JsonBuilder *hb = json_builder_new();
    json_builder_begin_object(hb);
    json_builder_set_member_name(hb, "role"); json_builder_add_string_value(hb, role);
    json_builder_set_member_name(hb, "content"); json_builder_add_string_value(hb, content);
    json_builder_end_object(hb);
    g_ptr_array_add(a->history, json_builder_get_root(hb));
    g_object_unref(hb);
}

static void send_message(App *a) {
    GtkTextBuffer *buf = gtk_text_view_get_buffer(GTK_TEXT_VIEW(a->input));
    GtkTextIter s, e; gtk_text_buffer_get_bounds(buf, &s, &e);
    char *msg = gtk_text_buffer_get_text(buf, &s, &e, FALSE);
    if (!msg || !*msg) { g_free(msg); return; }
    gtk_text_buffer_set_text(buf, "", -1);
    transcript_append(a, "you", msg);
    a->busy = TRUE; set_status(a, "Hyprneuro · thinking…");

    /* Build request with bounded history. */
    JsonBuilder *b = json_builder_new();
    json_builder_begin_object(b);
    json_builder_set_member_name(b, "action"); json_builder_add_string_value(b, "agent_chat");
    json_builder_set_member_name(b, "message"); json_builder_add_string_value(b, msg);
    json_builder_set_member_name(b, "max_tokens"); json_builder_add_int_value(b, 1024);
    json_builder_set_member_name(b, "history");
    json_builder_begin_array(b);
    for (guint i = 0; i < a->history->len; i++)
        json_builder_add_value(b, *(JsonNode **)g_ptr_array_index(a->history, i));
    json_builder_end_array(b);
    json_builder_end_object(b);
    JsonGenerator *g = json_generator_new();
    json_generator_set_root(g, json_builder_get_root(b));
    char *req = json_generator_to_data(g, NULL);
    char *frame = g_strconcat(req, "\n", NULL);
    char *msg_copy = g_strdup(msg);
    g_free(msg);

    a->sock = connect_sidecar(a);
    if (!a->sock) {
        set_status(a, "Hyprneuro · sidecar unavailable");
        a->busy = FALSE; g_free(frame); g_free(req);
        g_object_unref(g); g_object_unref(b); return;
    }
    gsize written;
    GOutputStream *out = g_io_stream_get_output_stream(G_IO_STREAM(a->sock));
    if (!g_output_stream_write_all(out, frame, strlen(frame), &written, NULL, NULL)) {
        set_status(a, "Hyprneuro · send failed"); a->busy = FALSE;
        g_free(frame); g_free(req); g_object_unref(g); g_object_unref(b); return;
    }
    g_free(frame); g_free(req); g_object_unref(g); g_object_unref(b);

    /* Read streaming frames, appending deltas live to the transcript. */
    GDataInputStream *stream = g_data_input_stream_new(g_io_stream_get_input_stream(G_IO_STREAM(a->sock)));
    GString *answer = g_string_new("");
    /* Start an assistant line. */
    GtkTextBuffer *tbuf = gtk_text_view_get_buffer(GTK_TEXT_VIEW(a->transcript));
    GtkTextIter tend; gtk_text_buffer_get_end_iter(tbuf, &tend);
    GtkTextTag *atag = gtk_text_buffer_create_tag(tbuf, "asst", "foreground", "#9ecbff",
        "weight", PANGO_WEIGHT_BOLD, NULL);
    gtk_text_buffer_insert_with_tags_by_name(tbuf, &tend, "\nassistant: ", -1, "asst", NULL);
    gboolean errored = FALSE;
    while (a->busy) {
        char *line = g_data_input_stream_read_line(stream, NULL, NULL, NULL);
        if (!line) break;
        JsonParser *p = json_parser_new();
        if (json_parser_load_from_data(p, line, -1, NULL)) {
            JsonNode *r = json_parser_get_root(p);
            JsonNode *tn = jmember(r, "type");
            const char *type = tn ? json_node_get_string(tn) : NULL;
            if (type && !g_strcmp0(type, "delta")) {
                JsonNode *dn = jmember(r, "text");
                const char *d = dn ? json_node_get_string(dn) : "";
                g_string_append(answer, d);
                gtk_text_buffer_get_end_iter(tbuf, &tend);
                gtk_text_buffer_insert(tbuf, &tend, d, -1);
                gtk_text_buffer_get_end_iter(tbuf, &tend);
                gtk_text_view_scroll_to_mark(GTK_TEXT_VIEW(a->transcript), NULL, 0, TRUE, 0, 1.0);
            } else if (type && !g_strcmp0(type, "error")) {
                errored = TRUE;
                const char *em = jmember(r, "error") ?
                    json_node_get_string(jmember(r, "error")) : "error";
                g_string_append_printf(answer, " [error: %s]", em);
                gtk_text_buffer_get_end_iter(tbuf, &tend);
                gtk_text_buffer_insert(tbuf, &tend, em, -1);
                break;
            } else if (type && !g_strcmp0(type, "done")) {
                break;
            }
        }
        g_object_unref(p); g_free(line);
        while (g_main_context_pending(g_main_context_default()))
            g_main_context_iteration(g_main_context_default(), FALSE);
    }
    g_object_unref(stream);
    a->busy = FALSE;
    set_status(a, errored ? "Hyprneuro · error" : "Hyprneuro · Local");

    /* Record the exchange in bounded history (keep last 10 turns). */
    push_history(a, "user", msg_copy);
    push_history(a, "assistant", answer->str);
    g_free(msg_copy);
    g_string_free(answer, TRUE);
    gtk_widget_grab_focus(GTK_WIDGET(a->input));
}

/* ---- monitoring status bar ---------------------------------------------- */
static gboolean poll_monitoring(gpointer data) {
    App *a = data;
    GError *err = NULL;
    char *mon_data = sidecar_call(a, "monitoring", NULL, &err);
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
    } else if (err) {
        gtk_label_set_text(GTK_LABEL(a->metrics), "sidecar offline");
        g_clear_error(&err);
    }
    return G_SOURCE_CONTINUE;
}

/* ---- show / hide --------------------------------------------------------- */
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

static gboolean on_key(GtkEventControllerKey *c, guint keyval, guint code, GdkModifierType state, gpointer data) {
    (void)c; (void)code; (void)state;
    App *a = data;
    if (keyval == GDK_KEY_Escape) { hide_ui(a); return TRUE; }
    return FALSE;
}

/* ---- control socket (ui.sock) ------------------------------------------- */
static void on_control_connect(GSocketService *svc, GSocketConnection *conn, GObject *source, gpointer data) {
    (void)svc; (void)source;
    App *a = data;
    GDataInputStream *in = g_data_input_stream_new(g_io_stream_get_input_stream(G_IO_STREAM(conn)));
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

/* ---- builder helpers ----------------------------------------------------- */
static GtkWidget *circular(GtkWidget *box, const char *icon, GCallback cb, App *a, const char *tip) {
    GtkWidget *btn = gtk_button_new_from_icon_name(icon);
    gtk_widget_add_css_class(btn, "jeevus-input-action");
    gtk_widget_set_valign(btn, GTK_ALIGN_CENTER);
    if (tip) gtk_widget_set_tooltip_text(btn, tip);
    g_signal_connect(btn, "clicked", cb, a);
    gtk_box_append(GTK_BOX(box), btn);
    return btn;
}

static void on_send(GtkButton *b, gpointer data) { (void)b; send_message(data); }
static void on_attach(GtkButton *b, gpointer data) { (void)b; (void)data; /* file picker: follow-up */ }
static void on_audio(GtkButton *b, gpointer data) { (void)b; (void)data; /* voice popovers: follow-up */ }
static void on_vision(GtkButton *b, gpointer data) { (void)b; (void)data; /* vision popovers: follow-up */ }
static void on_settings(GtkButton *b, gpointer data) { (void)b; (void)data; /* settings page: follow-up */ }

static void on_size_toggle(GtkButton *b, gpointer data) {
    App *a = data;
    a->size = (a->size == SIZE_FULL) ? SIZE_COMPACT : SIZE_FULL;
    apply_transcript_size(a);
    gtk_button_set_icon_name(b, a->size == SIZE_FULL ? "go-down-symbolic" : "go-up-symbolic");
}

/* ---- main ---------------------------------------------------------------- */
int main(int argc, char **argv) {
    (void)argc; (void)argv;
    gtk_init();
    App *a = g_new0(App, 1);
    a->size = SIZE_RESTORE;
    a->history = g_ptr_array_new_with_free_func((GDestroyNotify)json_node_free);
    a->sidecar_sock = g_strdup(g_getenv("HYPHARNESS_SIDECAR"));
    if (!a->sidecar_sock)
        a->sidecar_sock = g_build_filename(g_get_user_runtime_dir(), "hyprharness", "sidecar.sock", NULL);
    a->control_sock = g_build_filename(g_get_user_runtime_dir(), "hyprneuro", "ui.sock", NULL);

    /* CSS: transparent window + dark translucent panel (Jeevus design). */
    GtkCssProvider *css = gtk_css_provider_new();
    gtk_css_provider_load_from_string(css,
        "window.hn-transparent { background: transparent; box-shadow: none; }"
        ".hn-panel { background-color: alpha(@theme_bg_color,0.96); color: @theme_fg_color;"
        " border: 1px solid alpha(@theme_fg_color,0.18); border-radius: 16px; padding: 12px; }"
        ".hn-panel textview, .hn-panel textview text { background: transparent; color: @theme_fg_color; }"
        "textview.hn-composer, textview.hn-composer text { background-color: #272727; color: #f0f0f0; caret-color: #f0f0f0; }"
        ".hn-composer { border-radius: 8px; padding: 8px; }"
        ".hn-input-action, .hn-input-action > button { min-width: 40px; min-height: 40px; padding: 0; border-radius: 999px; }"
        ".hn-status { font-size: 0.85em; }");
    gtk_style_context_add_provider_for_display(gdk_display_get_default(),
        GTK_STYLE_PROVIDER(css), GTK_STYLE_PROVIDER_PRIORITY_APPLICATION);
    GtkCssProvider *alpha = gtk_css_provider_new();
    gtk_css_provider_load_from_string(alpha,
        "window.background.hn-transparent { background-color: rgba(0,0,0,0); background-image: none;"
        " border: none; outline: none; box-shadow: none; }");
    gtk_style_context_add_provider_for_display(gdk_display_get_default(),
        GTK_STYLE_PROVIDER(alpha), GTK_STYLE_PROVIDER_PRIORITY_USER);
    g_object_unref(css); g_object_unref(alpha);

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

    /* Panel layout. */
    a->panel = gtk_box_new(GTK_ORIENTATION_VERTICAL, 8);
    gtk_widget_add_css_class(a->panel, "hn-panel");
    gtk_window_set_child(a->win, a->panel);

    /* Transcript (scrolled text view). */
    a->transcript = gtk_text_view_new();
    gtk_text_view_set_editable(GTK_TEXT_VIEW(a->transcript), FALSE);
    gtk_text_view_set_wrap_mode(GTK_TEXT_VIEW(a->transcript), GTK_WRAP_WORD_CHAR);
    a->scroller = gtk_scrolled_window_new();
    gtk_scrolled_window_set_child(GTK_SCROLLED_WINDOW(a->scroller), a->transcript);
    gtk_scrolled_window_set_policy(GTK_SCROLLED_WINDOW(a->scroller),
        GTK_POLICY_NEVER, GTK_POLICY_AUTOMATIC);
    gtk_scrolled_window_set_max_content_height(GTK_SCROLLED_WINDOW(a->scroller), DEFAULT_WIDTH / 2);
    GtkAdjustment *vadj = gtk_scrolled_window_get_vadjustment(GTK_SCROLLED_WINDOW(a->scroller));
    g_signal_connect(vadj, "value-changed", G_CALLBACK(on_scroll_adjustment), a);
    gtk_box_append(GTK_BOX(a->panel), a->scroller);

    /* Composer. */
    a->composer = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 6);
    gtk_widget_add_css_class(a->composer, "hn-composer");
    a->attach = circular(a->composer, "list-add-symbolic", G_CALLBACK(on_attach), a, "Attach");
    a->input = GTK_TEXT_VIEW(gtk_text_view_new());
    gtk_widget_add_css_class(GTK_WIDGET(a->input), "hn-composer");
    gtk_text_view_set_wrap_mode(a->input, GTK_WRAP_WORD_CHAR);
    gtk_widget_set_hexpand(GTK_WIDGET(a->input), TRUE);
    gtk_widget_set_size_request(GTK_WIDGET(a->input), -1, 40);
    gtk_box_append(GTK_BOX(a->composer), GTK_WIDGET(a->input));
    a->send = circular(a->composer, "media-playback-start-symbolic", G_CALLBACK(on_send), a, "Send");
    a->audio = circular(a->composer, "microphone-sensitivity-high-symbolic", G_CALLBACK(on_audio), a, "Audio");
    a->vision = circular(a->composer, "camera-photo-symbolic", G_CALLBACK(on_vision), a, "Vision");
    a->size_toggle = circular(a->composer, "go-up-symbolic", G_CALLBACK(on_size_toggle), a, "Transcript size");
    circular(a->composer, "emblem-system-symbolic", G_CALLBACK(on_settings), a, "Settings");
    gtk_box_append(GTK_BOX(a->panel), a->composer);

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
    gtk_box_append(GTK_BOX(a->panel), statusrow);

    apply_transcript_size(a);

    /* Escape to hide. */
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
    return 0;
}
