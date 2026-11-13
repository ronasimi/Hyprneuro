/* Private inherited pipes to the asynchronous established-client adapter.
 * No credential handling, owner creation, lifecycle or text-as-command parsing
 * occurs on this path. All callbacks below execute on GTK's main context. */
#define PI_FRAME_MAX 65536

static const char *pi_observed_state(JsonNode *status) {
    const char *state = jstr(jmember(status, "state"));
    const char *phase = jstr(jmember(status, "owner_phase"));
    if (!g_strcmp0(phase, "failed") || !g_strcmp0(state, "failed")) return "failed";
    if (!g_strcmp0(phase, "transition") || !g_strcmp0(state, "transition")) return "transition";
    if (!g_strcmp0(state, "on")) return !g_strcmp0(phase, "hermes") ? "on" : "failed";
    if (!g_strcmp0(state, "off")) return !g_strcmp0(phase, "ordinary") ? "off" : "failed";
    return "unavailable";
}

/* Explicit authenticated owner mode, never infer ordinary safety from an
 * unavailable lifecycle alone. Failed/transition/malformed status stays closed. */
static gboolean pi_normal_only_ready(JsonNode *status) {
    JsonNode *mode = jmember(status, "normal_only");
    return mode && JSON_NODE_HOLDS_VALUE(mode) && json_node_get_value_type(mode) == G_TYPE_BOOLEAN &&
        json_node_get_boolean(mode) && !g_strcmp0(jstr(jmember(status, "state")), "unavailable") &&
        !g_strcmp0(jstr(jmember(status, "owner_phase")), "ordinary");
}

static gboolean pi_route_allowed(App *a, gboolean native) {
    if (!a->pi_optin) return TRUE;
    if (!a->pi_connected) return FALSE;
    if (a->pi_normal_only && !a->pi_transition && !g_strcmp0(a->pi_state, "unavailable")) return TRUE;
    if (native) return !g_strcmp0(a->pi_state, "off") || !g_strcmp0(a->pi_state, "on") ||
        !g_strcmp0(a->pi_state, "transition");
    return !a->pi_transition && !g_strcmp0(a->pi_state, "off");
}
static void pi_route_update(App *a) {
    if (!a->pi_route) return;
    gtk_label_set_text(GTK_LABEL(a->pi_route), a->attachment_b64 ?
        "Attachment → legacy sidecar · NO Pi tools/history · requires ordinary owner" :
        "Text → Pi owner · native tools require fresh host consent");
}

static void pi_finish_chat(App *a, gboolean success, const char *error) {
    if (!a->busy || !a->pi_chat) return;
    ChatDoneData *d = g_new0(ChatDoneData, 1);
    d->app = a; d->success = success && !a->pi_native_error;
    d->error = g_strdup(error ? error : "Native turn failed/aborted; inspect Pi session");
    on_chat_done(d);
}

static void pi_close_dialog(App *a) {
    if (a->pi_dialog) gtk_window_destroy(a->pi_dialog);
    a->pi_dialog = NULL;
    g_clear_pointer(&a->pi_consent_id, g_free);
}

static void pi_render(App *a) {
    gboolean on = !g_strcmp0(a->pi_state, "on");
    a->pi_rendering = TRUE;
    gtk_switch_set_active(a->pi_switch, on);
    gtk_switch_set_state(a->pi_switch, on);
    a->pi_rendering = FALSE;
    gtk_widget_set_sensitive(GTK_WIDGET(a->pi_switch), a->pi_connected &&
        !a->pi_transition && (!g_strcmp0(a->pi_state, "off") || on));
    char *label = g_strdup_printf("MoE · %s%s", a->pi_state,
        a->pi_transition ? " · transition request pending" : a->pi_normal_only ? " · normal-only" : "");
    gtk_label_set_text(GTK_LABEL(a->pi_label), label);
    gtk_accessible_update_property(GTK_ACCESSIBLE(a->pi_switch),
        GTK_ACCESSIBLE_PROPERTY_DESCRIPTION, label, -1);
    g_free(label);
}

static void pi_unavailable(App *a) {
    if (a->pi_dead) return;
    a->pi_dead = TRUE;
    if (a->pi_io) g_cancellable_cancel(a->pi_io);
    a->pi_normal_only = FALSE; a->pi_connected = FALSE; a->pi_transition = FALSE;
    a->pi_on_pending = a->pi_off_pending = FALSE;
    g_free(a->pi_state); a->pi_state = g_strdup("unavailable");
    pi_close_dialog(a); pi_render(a);
    pi_finish_chat(a, FALSE, "Pi disconnected/unavailable; outcome may be unknown. No retry/fallback.");
    if (a->pi_out) g_output_stream_close(a->pi_out, NULL, NULL); /* EOF → owner cleanup */
}

static void pi_write_next(App *a);
static void pi_written(GObject *object, GAsyncResult *result, gpointer data) {
    App *a = data;
    gboolean ok = g_output_stream_write_all_finish(G_OUTPUT_STREAM(object), result, NULL, NULL);
    g_bytes_unref(g_queue_pop_head(&a->pi_writes));
    a->pi_writing = FALSE;
    if (!ok) pi_unavailable(a);
    if (a->pi_dead) {
        /* close() during an outstanding write may return PENDING. Now the
         * write has settled, guarantee EOF so the adapter drops control auth. */
        g_output_stream_close(a->pi_out, NULL, NULL);
        g_queue_clear_full(&a->pi_writes, (GDestroyNotify)g_bytes_unref);
        return;
    }
    pi_write_next(a);
}
static void pi_write_next(App *a) {
    if (a->pi_writing || g_queue_is_empty(&a->pi_writes) || !a->pi_connected) return;
    GBytes *bytes = g_queue_peek_head(&a->pi_writes);
    gsize size; const void *data = g_bytes_get_data(bytes, &size);
    a->pi_writing = TRUE;
    g_output_stream_write_all_async(a->pi_out, data, size, G_PRIORITY_DEFAULT,
        a->pi_io, pi_written, a);
}
/* The pipe frame uses this same encoder for preflight and submission. */
static char *pi_encode_frame(const char *op, const char *text, gboolean allowed) {
    JsonBuilder *b = json_builder_new();
    json_builder_begin_object(b);
    json_builder_set_member_name(b, "op"); json_builder_add_string_value(b, op);
    if (text) {
        json_builder_set_member_name(b, !strcmp(op, "consent") ? "answer_id" : "text");
        json_builder_add_string_value(b, text);
    }
    if (!strcmp(op, "consent")) {
        json_builder_set_member_name(b, "allowed"); json_builder_add_boolean_value(b, allowed);
    }
    json_builder_end_object(b);
    JsonNode *root = json_builder_get_root(b);
    JsonGenerator *g = json_generator_new(); json_generator_set_root(g, root);
    char *json = json_generator_to_data(g, NULL);
    char *line = g_strconcat(json, "\n", NULL);
    g_free(json); json_node_unref(root); g_object_unref(g); g_object_unref(b);
    return line;
}

/* Match Python ensure_ascii=False/default separators and the owner's JS .length.
 * The owner envelope includes its fixed32-byte hex request ID and final newline.
 * Count JSON control/quote/backslash escapes, not just raw UTF-8 text bytes. */
static gboolean pi_clear_valid_draft(GtkTextBuffer *composer, const char *text) {
    if (!g_utf8_validate(text, -1, NULL)) return FALSE;
    gsize bytes = sizeof("{\"op\": \"chat\", \"id\": \"00000000000000000000000000000000\", \"text\": \"\"}\n") - 1;
    guint units = 0;
    gboolean nonblank = FALSE;
    for (const char *p = text; *p; p = g_utf8_next_char(p)) {
        gunichar ch = g_utf8_get_char(p);
        units += ch > 0xffff ? 2 : 1;
        if (ch == '"' || ch == '\\' || ch == '\b' || ch == '\f' || ch == '\n' || ch == '\r' || ch == '\t')
            bytes += 2;
        else bytes += ch < 0x20 ? 6 : g_utf8_next_char(p) - p;
        if (units > 16000 || bytes > PI_FRAME_MAX) return FALSE;
        /* Reject Python-strip or ECMAScript-trim-only drafts before clearing. */
        if (!g_unichar_isspace(ch) && ch != 0xfeff && !(ch >= 0x1c && ch <= 0x1f)) nonblank = TRUE;
    }
    if (!nonblank) return FALSE;
    char *frame = pi_encode_frame("chat", text, FALSE);
    gboolean fits = strlen(frame) <= PI_FRAME_MAX;
    g_free(frame);
    if (fits) gtk_text_buffer_set_text(composer, "", -1);
    return fits;
}

static void pi_send(App *a, const char *op, const char *text, gboolean allowed) {
    if (!a->pi_connected || g_queue_get_length(&a->pi_writes) >= 8) {
        pi_unavailable(a); return;
    }
    char *line = pi_encode_frame(op, text, allowed);
    if (strlen(line) <= PI_FRAME_MAX) {
        g_queue_push_tail(&a->pi_writes, g_bytes_new_take(line, strlen(line)));
        pi_write_next(a);
    } else { g_free(line); pi_finish_chat(a, FALSE, "Pi frame exceeds bound; draft was not submitted"); }
}
static void pi_send_text(App *a, const char *text) { pi_send(a, "chat", text, FALSE); }

static void pi_control(App *a, const char *op) {
    if (!a->pi_connected) { set_status(a, "Pi unavailable · explicit opt-in and existing owner required"); return; }
    if (strcmp(op, "status") && a->pi_normal_only) { set_status(a, "Lifecycle unavailable · normal-only owner; text/read remains available"); return; }
    if (strcmp(op, "status") && a->busy && !a->pi_chat) {
        set_status(a, "Wait for legacy media/chat before changing residency"); return;
    }
    if (!strcmp(op, "on") && (a->pi_transition || g_strcmp0(a->pi_state, "off"))) {
        set_status(a, "MoE on refused · observed state not off"); return;
    }
    if (!strcmp(op, "off") && a->pi_off_pending) return;
    if (strcmp(op, "status")) {
        if (!strcmp(op, "on")) a->pi_on_pending = TRUE;
        else a->pi_off_pending = TRUE;
        a->pi_transition = TRUE; pi_render(a);
    }
    pi_send(a, op, NULL, FALSE);
}
static gboolean pi_switch_change(GtkSwitch *sw, gboolean state, gpointer data) {
    (void)sw; App *a = data;
    if (!a->pi_rendering) pi_control(a, state ? "on" : "off");
    return TRUE; /* Never optimistic: active/state are set by observed status. */
}
static void pi_cancel_chat(GtkButton *button, gpointer data) {
    (void)button; App *a = data;
    gtk_widget_set_sensitive(a->pi_cancel, FALSE);
    set_status(a, "Pi cancel requested · outcome may be unknown");
    pi_send(a, "cancel", NULL, FALSE);
}
static void pi_cancel_on(GtkButton *button, gpointer data) {
    (void)button; pi_control(data, "off");
}

/* Only the composer submission boundary calls this. No assistant/event text
 * reaches it. Exact typed user commands are controls, not native prompts. */
static const char *pi_command(const char *text) {
    if (!g_strcmp0(text, "/moe on")) return "on";
    if (!g_strcmp0(text, "/moe off")) return "off";
    if (!g_strcmp0(text, "/moe status")) return "status";
    return NULL;
}
static gboolean pi_typed_command(App *a) {
    /* Unit helper busy guard uses no display-backed input. */
    if (!a->input) return FALSE;
    GtkTextBuffer *buf = gtk_text_view_get_buffer(a->input);
    GtkTextIter s, e; gtk_text_buffer_get_bounds(buf, &s, &e);
    char *text = gtk_text_buffer_get_text(buf, &s, &e, FALSE);
    const char *op = pi_command(text);
    gboolean command = op || !strcmp(text, "/moe") || g_str_has_prefix(text, "/moe ");
    if (command) {
        if (op) { pi_control(a, op); gtk_text_buffer_set_text(buf, "", -1); }
        else set_status(a, "Use exact /moe on, /moe off, or /moe status");
    }
    g_free(text); return command;
}

static void pi_consent_answer(GtkButton *button, gpointer data) {
    App *a = data;
    gboolean allowed = GPOINTER_TO_INT(g_object_get_data(G_OBJECT(button), "pi-allow"));
    if (a->pi_consent_id) pi_send(a, "consent", a->pi_consent_id, allowed);
    pi_close_dialog(a);
}
static gboolean pi_consent_close(GtkWindow *window, gpointer data) {
    (void)window; App *a = data;
    if (a->pi_consent_id) pi_send(a, "consent", a->pi_consent_id, FALSE);
    pi_close_dialog(a); return TRUE;
}
static gboolean pi_consent_key(GtkEventControllerKey *controller, guint key, guint code,
                                GdkModifierType state, gpointer data) {
    (void)controller; (void)code; (void)state;
    if (key != GDK_KEY_Escape) return FALSE;
    App *a = data; pi_consent_close(a->pi_dialog, a); return TRUE;
}
static void pi_consent(App *a, JsonNode *event) {
    const char *id = jstr(jmember(event, "id")), *title = jstr(jmember(event, "title"));
    const char *detail = jstr(jmember(event, "detail"));
    if (!id || !title || !detail || strlen(id)>80 || strlen(title)>1200 || strlen(detail)>96000) {
        pi_unavailable(a); return;
    }
    if (a->pi_consent_id || !a->shown) { pi_send(a, "consent", id, FALSE); return; }
    a->pi_consent_id = g_strdup(id);
    a->pi_dialog = GTK_WINDOW(gtk_window_new());
    gtk_window_set_title(a->pi_dialog, "Pi host consent · fresh human decision");
    gtk_window_set_transient_for(a->pi_dialog, a->win);
    /* Non-modal: drafts/chat may be submitted while an on request waits. The
     * owner serializes it; a pending chat never allows a second chat submission. */
    gtk_window_set_default_size(a->pi_dialog, 560, 360);
    GtkWidget *box = gtk_box_new(GTK_ORIENTATION_VERTICAL, 8);
    gtk_window_set_child(a->pi_dialog, box);
    GtkWidget *heading = gtk_label_new(title);
    gtk_label_set_wrap(GTK_LABEL(heading), TRUE); gtk_box_append(GTK_BOX(box), heading);
    GtkWidget *warning = gtk_label_new("Host request, not model approval. Exact task/action details below. Deny is safe; Bash/command execution is UNSANDBOXED.");
    gtk_label_set_wrap(GTK_LABEL(warning), TRUE); gtk_box_append(GTK_BOX(box), warning);
    GtkWidget *scroll = gtk_scrolled_window_new(); gtk_widget_set_vexpand(scroll, TRUE);
    GtkWidget *view = gtk_text_view_new(); gtk_text_view_set_editable(GTK_TEXT_VIEW(view), FALSE);
    gtk_text_view_set_wrap_mode(GTK_TEXT_VIEW(view), GTK_WRAP_WORD_CHAR);
    gtk_text_buffer_set_text(gtk_text_view_get_buffer(GTK_TEXT_VIEW(view)), detail, -1);
    gtk_scrolled_window_set_child(GTK_SCROLLED_WINDOW(scroll), view); gtk_box_append(GTK_BOX(box), scroll);
    GtkWidget *buttons = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 8);
    gtk_box_append(GTK_BOX(box), buttons);
    const char *names[] = {"Deny", "Allow exact action once"};
    for (int i=0; i<2; i++) {
        GtkWidget *b = gtk_button_new_with_label(names[i]);
        g_object_set_data(G_OBJECT(b), "pi-allow", GINT_TO_POINTER(i));
        g_signal_connect(b, "clicked", G_CALLBACK(pi_consent_answer), a);
        gtk_box_append(GTK_BOX(buttons), b);
        if (!i) gtk_window_set_default_widget(a->pi_dialog, b);
    }
    g_signal_connect(a->pi_dialog, "close-request", G_CALLBACK(pi_consent_close), a);
    GtkEventController *key = gtk_event_controller_key_new();
    g_signal_connect(key, "key-pressed", G_CALLBACK(pi_consent_key), a);
    gtk_widget_add_controller(GTK_WIDGET(a->pi_dialog), key);
    gtk_window_present(a->pi_dialog);
}

static void pi_packet(App *a, JsonNode *packet) {
    if (a->pi_dead) return; /* Late buffered status/events cannot resurrect a disconnect. */
    const char *type = jstr(jmember(packet, "type"));
    const char *op = jstr(jmember(packet, "op"));
    if (!g_strcmp0(type, "connected")) { a->pi_connected = TRUE; pi_render(a); }
    else if (!g_strcmp0(type, "status")) {
        a->pi_normal_only = pi_normal_only_ready(jmember(packet, "result"));
        g_free(a->pi_state); a->pi_state = g_strdup(pi_observed_state(jmember(packet, "result")));
        pi_render(a);
    } else if (!g_strcmp0(type, "host_event")) {
        JsonNode *event = jmember(packet, "event");
        if (!g_strcmp0(jstr(jmember(event, "type")), "consent")) pi_consent(a, event);
        /* Routing recommendation never grants approval or triggers controls. */
    } else if (!g_strcmp0(type, "consent_closed")) {
        if (!g_strcmp0(a->pi_consent_id, jstr(jmember(packet, "answer_id")))) pi_close_dialog(a);
    } else if (!g_strcmp0(type, "event") && a->pi_chat && a->busy) {
        JsonNode *event = jmember(packet, "event");
        const char *kind = jstr(jmember(event, "type"));
        const char *text = jstr(jmember(event, "text"));
        if (!g_strcmp0(kind, "delta") && text) {
            render_delta(a, gtk_text_view_get_buffer(GTK_TEXT_VIEW(a->transcript)), text,
                !g_strcmp0(jstr(jmember(event, "channel")), "reasoning"));
            transcript_scroll_to_bottom(a);
        } else if (!g_strcmp0(kind, "turn_end")) {
            const char *stop = jstr(jmember(event, "stopReason"));
            if (!g_strcmp0(stop, "error") || !g_strcmp0(stop, "aborted")) a->pi_native_error = TRUE;
        } else if (!g_strcmp0(kind, "tool_execution_start") || !g_strcmp0(kind, "tool_execution_end")) {
            const char *tool = jstr(jmember(event, "tool"));
            JsonNode *err = jmember(event, "isError");
            char *status = g_strdup_printf("Pi tool %.80s · %s%s", tool ? tool : "unknown", kind,
                jboolean(err) && json_node_get_boolean(err) ? " · FAILED" : "");
            set_status(a, status); transcript_append(a, "Pi tool", status); g_free(status);
        }
    } else if (!g_strcmp0(type, "result") || !g_strcmp0(type, "error")) {
        gboolean ok = !strcmp(type, "result");
        if (!g_strcmp0(op, "chat")) {
            JsonNode *settled = jmember(jmember(packet, "result"), "settled");
            pi_finish_chat(a, ok && jboolean(settled) && json_node_get_boolean(settled),
                ok ? NULL : "Pi request failed/interrupted; review native session. No retry.");
        } else if (!g_strcmp0(op, "on") || !g_strcmp0(op, "off")) {
            if (!strcmp(op, "on")) a->pi_on_pending = FALSE;
            else a->pi_off_pending = FALSE;
            a->pi_transition = a->pi_on_pending || a->pi_off_pending;
            if (!ok) { g_free(a->pi_state); a->pi_state = g_strdup("failed"); }
            pi_render(a);
        }
        if (!ok) set_status(a, "Pi request failed · review owner/checkpoint · no retry");
    } else if (!g_strcmp0(type, "notice")) {
        set_status(a, "Pi consent denied: action details exceeded display bound");
    } else if (!g_strcmp0(type, "unavailable")) pi_unavailable(a);
}

static void pi_read_next(App *a);
static void pi_read(GObject *object, GAsyncResult *result, gpointer data) {
    App *a = data;
    gssize n = g_input_stream_read_finish(G_INPUT_STREAM(object), result, NULL);
    if (n <= 0) { pi_unavailable(a); return; }
    for (gssize i=0; i<n; i++) {
        char c = a->pi_buffer[i];
        if (c == '\n') {
            JsonParser *p = json_parser_new();
            gboolean valid = json_parser_load_from_data(p, a->pi_frame->str, a->pi_frame->len, NULL) &&
                JSON_NODE_HOLDS_OBJECT(json_parser_get_root(p));
            if (valid) pi_packet(a, json_parser_get_root(p));
            g_object_unref(p); g_string_truncate(a->pi_frame, 0);
            if (!valid) { pi_unavailable(a); return; }
            if (a->pi_dead) return;
        } else {
            if (!c || a->pi_frame->len >= PI_FRAME_MAX - 1) { pi_unavailable(a); return; }
            g_string_append_c(a->pi_frame, c);
        }
    }
    pi_read_next(a);
}
static void pi_read_next(App *a) {
    g_input_stream_read_async(a->pi_in, a->pi_buffer, sizeof a->pi_buffer,
        G_PRIORITY_DEFAULT, a->pi_io, pi_read, a);
}
static void pi_start(App *a) {
    if (!a->pi_optin) return;
    const char *python = g_getenv("HYPRNEURO_PI_BRIDGE_PYTHON");
    if (!python) python = "python3";
    a->pi_process = g_subprocess_new(G_SUBPROCESS_FLAGS_STDIN_PIPE | G_SUBPROCESS_FLAGS_STDOUT_PIPE |
        G_SUBPROCESS_FLAGS_STDERR_SILENCE, NULL, python, "-m", "hyprneuro.pi_desktop_bridge", NULL);
    if (!a->pi_process) { pi_unavailable(a); return; }
    a->pi_in = g_subprocess_get_stdout_pipe(a->pi_process);
    a->pi_out = g_subprocess_get_stdin_pipe(a->pi_process);
    a->pi_io = g_cancellable_new(); a->pi_frame = g_string_new("");
    pi_read_next(a);
}
static void pi_stop(App *a) {
    pi_close_dialog(a);
    if (a->pi_io) g_cancellable_cancel(a->pi_io);
    if (a->pi_out) g_output_stream_close(a->pi_out, NULL, NULL);
    /* EOF is deliberate last-control disconnect cleanup, not a forced kill. */
}
static void pi_build(App *a) {
    GtkWidget *row = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 8);
    a->pi_switch = GTK_SWITCH(gtk_switch_new());
    gtk_accessible_update_property(GTK_ACCESSIBLE(a->pi_switch), GTK_ACCESSIBLE_PROPERTY_LABEL, "MoE observed switch", -1);
    gtk_widget_set_tooltip_text(GTK_WIDGET(a->pi_switch), "Observed MoE state; each handoff needs fresh host consent");
    a->pi_label = gtk_label_new("MoE · unavailable");
    a->pi_cancel = gtk_button_new_with_label("Cancel Pi chat");
    gtk_widget_set_tooltip_text(a->pi_cancel, "Abort this chat connection and deny pending host consent; outcome may be unknown");
    GtkWidget *off = gtk_button_new_with_label("MoE off / cancel on");
    g_signal_connect(a->pi_switch, "state-set", G_CALLBACK(pi_switch_change), a);
    g_signal_connect(a->pi_cancel, "clicked", G_CALLBACK(pi_cancel_chat), a);
    g_signal_connect(off, "clicked", G_CALLBACK(pi_cancel_on), a);
    gtk_widget_set_sensitive(a->pi_cancel, FALSE);
    gtk_box_append(GTK_BOX(row), GTK_WIDGET(a->pi_switch));
    gtk_box_append(GTK_BOX(row), a->pi_label);
    gtk_box_append(GTK_BOX(row), off); gtk_box_append(GTK_BOX(row), a->pi_cancel);
    gtk_box_append(GTK_BOX(a->chat_page), row);
    gtk_widget_set_visible(row, a->pi_optin);
    a->pi_route = gtk_label_new(a->pi_optin ? "Text → Pi owner · attachments → legacy/tool-free (ordinary owner only)" : "Legacy sidecar · tool-free chat/media");
    gtk_label_set_wrap(GTK_LABEL(a->pi_route), TRUE);
    gtk_widget_add_css_class(a->pi_route, "dim-label");
    gtk_box_append(GTK_BOX(a->chat_page), a->pi_route);
    gtk_widget_set_visible(a->pi_route, a->pi_optin);
    pi_render(a);
}
